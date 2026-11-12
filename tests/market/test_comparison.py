from decimal import Decimal
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.market.models import Plan as LegacyPlan
from apps.market.models import Provider
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
)


@pytest.mark.django_db
def test_comparison_uses_published_pipeline_values_and_tolerates_missing_price(
    client, django_user_model
):
    user = django_user_model.objects.create_user("analyst@example.test", "password")
    first, first_plan, first_snapshot = _published_plan("first", with_price=True)
    second, second_plan, second_snapshot = _published_plan("second", with_price=False)
    definition = FeatureDefinition.objects.create(
        code="comparison-users",
        display_name="Usuarios totales",
        data_type=FeatureDefinition.DataType.INTEGER,
        unit="usuarios",
        scope=FeatureDefinition.Scope.CANONICAL,
        origin=FeatureDefinition.Origin.CONFIGURED,
    )
    for snapshot, users in ((first_snapshot, 1), (second_snapshot, 5)):
        PlanFeatureValue.objects.create(
            plan_snapshot=snapshot,
            feature_definition=definition,
            value_integer=users,
            availability=PlanFeatureValue.Availability.PRESENT,
            origin=PlanFeatureValue.Origin.RULE,
        )
    LegacyPlan.objects.create(
        provider=first,
        name="Plan heredado que no debe aparecer",
        stable_key="legacy-hidden",
    )
    client.force_login(user)

    response = client.get(
        reverse("comparison"),
        {"plan": [first_plan.id, second_plan.id]},
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Plan first" in content
    assert "Plan second" in content
    assert "USD 49,90" in content
    assert "Precio sin datos" in content
    assert "Usuarios totales" in content
    assert "1 usuarios" in content
    assert "5 usuarios" in content
    assert "Plan heredado que no debe aparecer" not in content


@pytest.mark.django_db
def test_comparison_normalizes_forged_cross_scope_plan(client, django_user_model):
    user = django_user_model.objects.create_user("comparison-filter@example.test", "password")
    demo_plan = MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).first()
    client.force_login(user)

    response = client.get(reverse("comparison"), {"preset": "all", "plan": demo_plan.id})

    assert response.status_code == 302
    assert response.url.startswith("/comparison/?preset=all&period=6")


def _published_plan(code: str, *, with_price: bool):
    provider = Provider.objects.create(name=f"Proveedor {code}", code=f"comparison-{code}")
    plan = MarketPlan.objects.create(
        provider=provider,
        external_key=f"{code}-plan",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    profile = PipelineProfile.objects.create(code=f"comparison-{uuid4()}", name="Perfil")
    version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    now = timezone.now()
    run = PipelineRun.objects.create(
        profile_version=version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=PipelineRun.Status.PUBLISHED,
        started_at=now,
        finished_at=now,
        published_at=now,
    )
    provider_run = ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=PipelineRun.Status.PUBLISHED,
        started_at=now,
        finished_at=now,
        published_at=now,
        is_complete=True,
    )
    snapshot = PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=now,
        plan_name=f"Plan {code}",
        product_code="Facturación",
    )
    if with_price:
        PlanPriceSnapshot.objects.create(
            plan_snapshot=snapshot,
            billing_period=PlanPriceSnapshot.BillingPeriod.MONTHLY,
            currency_code="USD",
            amount=Decimal("49.90"),
            effective_monthly_amount=Decimal("49.90"),
            source_kind=PlanPriceSnapshot.SourceKind.SCRAPED,
        )
    return provider, plan, snapshot
