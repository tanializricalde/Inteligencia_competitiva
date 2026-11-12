from decimal import Decimal
from uuid import uuid4

import pytest
from django.http import QueryDict
from django.urls import reverse
from django.utils import timezone

from apps.market.dashboard_service import (
    DashboardSelectionError,
    build_dashboard_data,
    resolve_dashboard_selection,
)
from apps.market.models import (
    DashboardPreset,
    DashboardPresetFeature,
    DashboardPresetProvider,
    Provider,
)
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanSnapshot,
    ProviderRun,
)


@pytest.mark.django_db
def test_matrix_preserves_typed_values_units_zero_and_distinct_missing_states():
    first, first_snapshot = _published_snapshot("typed-a")
    second, second_snapshot = _published_snapshot("typed-b")
    definitions = {
        "users": _definition("users-total", "Usuarios totales", "integer", "usuarios"),
        "percent": _definition("coverage", "Cobertura", "decimal", "%"),
        "money": _definition("extra-price", "Módulo adicional", "decimal", "USD"),
        "text": _definition("description", "Descripción", "string"),
        "boolean": _definition("support", "Soporte", "boolean"),
        "na": _definition("regional-tax", "Impuesto regional", "string"),
    }
    _value(first_snapshot, definitions["users"], value_integer=0)
    _value(second_snapshot, definitions["users"], value_integer=5)
    _value(first_snapshot, definitions["percent"], value_decimal=Decimal("80.500000"))
    _value(first_snapshot, definitions["money"], value_decimal=Decimal("25.000000"))
    _value(
        first_snapshot,
        definitions["text"],
        value_text="Valor textual suficientemente largo para truncarse sin romper la celda",
    )
    _value(
        first_snapshot,
        definitions["boolean"],
        value_boolean=False,
        availability="excluded",
    )
    _value(first_snapshot, definitions["na"], availability="not_applicable")

    selection = resolve_dashboard_selection(
        QueryDict(f"provider={first.code}&provider={second.code}")
    )
    rows = {row["code"]: row for row in build_dashboard_data(selection)["heatmap"]["rows"]}

    assert [cell["full_value"] for cell in rows["users-total"]["cells"]] == [
        "0 usuarios",
        "5 usuarios",
    ]
    assert rows["coverage"]["cells"][0]["full_value"] == "80.5 %"
    assert rows["extra-price"]["cells"][0]["full_value"] == "USD 25"
    assert rows["description"]["cells"][0]["value"].endswith("…")
    assert rows["description"]["cells"][1]["full_value"] == "Sin datos"
    assert rows["description"]["cells"][1]["state"] == "unknown"
    assert rows["support"]["cells"][0]["state"] == "unsupported"
    assert rows["support"]["cells"][0]["full_value"] == "No"
    assert rows["regional-tax"]["cells"][0]["state"] == "not_applicable"
    assert "Usuarios totales" in rows["users-total"]["cells"][0]["aria_label"]


@pytest.mark.django_db
def test_matrix_standardizes_boolean_summary_and_details_each_plan_in_tooltip():
    provider, first_snapshot = _published_snapshot("plan-details")
    first_snapshot.plan_name = "Plan A"
    first_snapshot.product_code = "producto-a"
    first_snapshot.save(update_fields=("plan_name", "product_code"))
    second_snapshot = _additional_snapshot(first_snapshot, "plan-b", "Plan B", "producto-b")
    third_snapshot = _additional_snapshot(first_snapshot, "plan-c", "Plan C")
    boolean = _definition("mixed-boolean", "Funcionalidad mixta", "boolean")
    numeric = _definition("mixed-limit", "Límite mixto", "integer", "usuarios")
    _value(
        first_snapshot,
        boolean,
        availability=PlanFeatureValue.Availability.EXCLUDED,
        value_boolean=False,
    )
    _value(second_snapshot, boolean, value_boolean=True)
    _value(
        third_snapshot,
        boolean,
        availability=PlanFeatureValue.Availability.UNKNOWN,
        origin=PlanFeatureValue.Origin.DEFAULT,
        value_boolean=False,
    )
    _value(first_snapshot, numeric, value_integer=5)
    _value(second_snapshot, numeric, value_integer=10)
    _value(
        third_snapshot,
        numeric,
        availability=PlanFeatureValue.Availability.UNKNOWN,
        origin=PlanFeatureValue.Origin.DEFAULT,
        value_integer=0,
    )

    selection = resolve_dashboard_selection(QueryDict(f"provider={provider.code}"))
    rows = {row["code"]: row for row in build_dashboard_data(selection)["heatmap"]["rows"]}
    boolean_cell = rows[boolean.code]["cells"][0]
    numeric_cell = rows[numeric.code]["cells"][0]

    assert boolean_cell["state"] == "limited"
    assert boolean_cell["full_value"] == "Sí · No"
    assert boolean_cell["detail"].splitlines() == [
        "Plan A (producto-a): No",
        "Plan B (producto-b): Sí",
        "Plan C: Sin datos",
    ]
    assert "detalle por plan: Plan A (producto-a): No" in boolean_cell["aria_label"]
    assert numeric_cell["state"] == "limited"
    assert numeric_cell["full_value"] == "5 usuarios · 10 usuarios"
    assert numeric_cell["detail"].splitlines() == [
        "Plan A (producto-a): 5 usuarios",
        "Plan B (producto-b): 10 usuarios",
        "Plan C: Sin datos",
    ]


@pytest.mark.django_db
def test_temporary_feature_filter_is_server_validated_and_can_be_explicitly_empty():
    provider, snapshot = _published_snapshot("filters")
    first = _definition("first-feature", "Primera", "boolean")
    second = _definition("second-feature", "Segunda", "boolean")
    _value(snapshot, first, value_boolean=True)
    _value(snapshot, second, value_boolean=True)

    selected = resolve_dashboard_selection(
        QueryDict(f"provider={provider.code}&feature_filter=1&feature={second.code}")
    )
    empty = resolve_dashboard_selection(QueryDict(f"provider={provider.code}&feature_filter=1"))

    assert [feature.code for feature in selected.features] == [second.code]
    assert selected.feature_filter_active is True
    assert "feature=second-feature" in selected.canonical_query
    assert empty.features == ()
    assert empty.temporary_filters is True
    with pytest.raises(DashboardSelectionError, match="no pertenecen"):
        resolve_dashboard_selection(
            QueryDict(f"provider={provider.code}&feature_filter=1&feature=forged")
        )


@pytest.mark.django_db
def test_all_unknown_feature_is_hidden_by_default_but_remains_explicitly_selectable():
    provider, snapshot = _published_snapshot("unknown-visibility")
    unknown = _definition("cost-center", "Centro de costos", "boolean")
    evidenced = _definition("api-access", "Acceso API", "boolean")
    _value(
        snapshot,
        unknown,
        availability=PlanFeatureValue.Availability.UNKNOWN,
        origin=PlanFeatureValue.Origin.DEFAULT,
        value_boolean=False,
    )
    _value(
        snapshot,
        evidenced,
        availability=PlanFeatureValue.Availability.EXCLUDED,
        value_boolean=False,
    )

    default_selection = resolve_dashboard_selection(QueryDict(f"provider={provider.code}"))
    filtered_selection = resolve_dashboard_selection(
        QueryDict(f"provider={provider.code}&feature_filter=1&feature={unknown.code}")
    )
    preset = DashboardPreset.objects.create(
        name="Centro de costos explícito",
        slug="explicit-cost-center",
        feature_selection=DashboardPreset.FeatureSelection.EXPLICIT,
    )
    DashboardPresetProvider.objects.create(preset=preset, provider=provider)
    DashboardPresetFeature.objects.create(
        preset=preset,
        feature_definition=unknown,
        position=0,
    )
    preset_selection = resolve_dashboard_selection(QueryDict(f"preset={preset.slug}"))

    assert [feature.code for feature in default_selection.available_features] == [
        evidenced.code,
        unknown.code,
    ]
    assert default_selection.features == (evidenced,)
    assert filtered_selection.features == (unknown,)
    assert preset_selection.features == (unknown,)
    row = build_dashboard_data(filtered_selection)["heatmap"]["rows"][0]
    assert row["cells"][0]["state"] == "unknown"
    assert row["cells"][0]["full_value"] == "Sin datos"


@pytest.mark.django_db
def test_explicit_preset_intersects_inactive_features_and_deletion_is_safe():
    provider, snapshot = _published_snapshot("preset-features")
    active = _definition("active-feature", "Activa", "boolean")
    obsolete = _definition("obsolete-feature", "Obsoleta", "boolean")
    _value(snapshot, active, value_boolean=True)
    obsolete_value = _value(snapshot, obsolete, value_boolean=True)
    preset = DashboardPreset.objects.create(
        name="Funciones elegidas",
        slug="selected-features",
        feature_selection=DashboardPreset.FeatureSelection.EXPLICIT,
    )
    DashboardPresetProvider.objects.create(preset=preset, provider=provider)
    DashboardPresetFeature.objects.create(preset=preset, feature_definition=active, position=0)
    DashboardPresetFeature.objects.create(preset=preset, feature_definition=obsolete, position=1)
    obsolete.is_active = False
    obsolete.save(update_fields=("is_active",))

    selection = resolve_dashboard_selection(QueryDict(f"preset={preset.slug}"))

    assert selection.features == (active,)
    assert selection.notices == ("Algunas características guardadas ya no están disponibles",)
    obsolete_id = obsolete.id
    obsolete_value.delete()
    obsolete.delete()
    assert not DashboardPresetFeature.objects.filter(
        preset=preset, feature_definition_id=obsolete_id
    ).exists()


@pytest.mark.django_db
def test_matrix_filter_controls_and_accessible_typed_cell_render_without_mutating_preset(
    client, django_user_model
):
    provider, snapshot = _published_snapshot("matrix-ui")
    definition = _definition("matrix-users", "Usuarios totales", "integer", "usuarios")
    _value(snapshot, definition, value_integer=0)
    user = django_user_model.objects.create_user("matrix@example.test", "password")
    client.force_login(user)

    response = client.get(
        reverse("dashboard"),
        {
            "provider": provider.code,
            "feature_filter": "1",
            "feature": definition.code,
        },
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Filtrar características" in content
    assert "Seleccionar todas" in content
    assert "Limpiar selección" in content
    assert "Restablecer" in content
    assert "data-feature-search" in content
    assert 'class="heat-cell heat-supported" tabindex="0"' in content
    assert 'title="Plan matrix-ui: 0 usuarios"' in content
    assert "valor 0 usuarios" in content
    assert "0 usuarios" in content
    assert not DashboardPresetFeature.objects.exists()

    empty = client.get(
        reverse("dashboard"),
        {"provider": provider.code, "feature_filter": "1"},
    ).content.decode()
    assert "0 de 1 visibles" in empty
    assert "No hay características con datos para estos planes." in empty


def _published_snapshot(code: str) -> tuple[Provider, PlanSnapshot]:
    provider = Provider.objects.create(name=f"Proveedor {code}", code=code)
    plan = MarketPlan.objects.create(
        provider=provider,
        external_key=f"{code}-plan",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    profile = PipelineProfile.objects.create(code=f"profile-{uuid4()}", name="Perfil")
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
    return provider, PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=now,
        plan_name=f"Plan {code}",
    )


def _definition(code: str, name: str, data_type: str, unit: str | None = None):
    return FeatureDefinition.objects.create(
        code=code,
        display_name=name,
        data_type=data_type,
        unit=unit,
        scope=FeatureDefinition.Scope.CANONICAL,
        origin=FeatureDefinition.Origin.CONFIGURED,
    )


def _additional_snapshot(
    base_snapshot: PlanSnapshot,
    external_key: str,
    plan_name: str,
    product_code: str = "",
) -> PlanSnapshot:
    plan = MarketPlan.objects.create(
        provider=base_snapshot.provider_run.provider,
        external_key=external_key,
        first_seen_at=base_snapshot.observed_at,
        last_seen_at=base_snapshot.observed_at,
    )
    return PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=base_snapshot.provider_run,
        observed_at=base_snapshot.observed_at,
        plan_name=plan_name,
        product_code=product_code,
    )


def _value(
    snapshot,
    definition,
    availability="present",
    origin=PlanFeatureValue.Origin.RULE,
    **typed_value,
):
    return PlanFeatureValue.objects.create(
        plan_snapshot=snapshot,
        feature_definition=definition,
        availability=availability,
        origin=origin,
        **typed_value,
    )
