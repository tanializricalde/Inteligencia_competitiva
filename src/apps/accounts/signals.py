from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.db.models.signals import post_migrate


def ensure_default_groups(**_kwargs) -> None:
    if not apps.ready:
        return
    analyst_permissions = Permission.objects.filter(
        Q(content_type__app_label="market", codename__startswith="view_")
        | Q(
            content_type__app_label="reviews",
            codename__in=(
                "export_reviews",
                "view_marketreview",
                "view_reviewobservation",
                "view_reviewenrichment",
            ),
        )
    )
    operator_permissions = Permission.objects.filter(
        Q(
            content_type__app_label="pipeline",
            codename__in=("add_pipelinerun", "view_pipelinerun", "view_marketsource"),
        )
    )
    definitions = {
        "Administrador": Permission.objects.all(),
        "Analista": analyst_permissions,
        "Operador": Permission.objects.filter(
            Q(pk__in=analyst_permissions.values("pk")) | Q(pk__in=operator_permissions.values("pk"))
        ),
    }
    for name, permissions in definitions.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(permissions)


post_migrate.connect(ensure_default_groups, dispatch_uid="accounts.ensure_default_groups")
