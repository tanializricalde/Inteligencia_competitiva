from django import forms

from apps.form_styling import StyledFormMixin
from apps.market.models import Provider
from apps.reviews.infrastructure.registry import review_adapter_keys
from apps.reviews.models import ReviewSource


class ReviewSourceForm(StyledFormMixin, forms.ModelForm):
    adapter_key = forms.ChoiceField(label="Adaptador", choices=())

    class Meta:
        model = ReviewSource
        fields = (
            "provider",
            "name",
            "platform",
            "adapter_key",
            "source_url",
            "external_entity_id",
            "country_code",
            "enabled",
            "schedule_enabled",
            "request_delay_seconds",
            "timeout_seconds",
            "retry_limit",
            "max_pages",
            "max_reviews",
            "review_window",
            "adapter_config",
        )
        labels = {
            "provider": "Competidor",
            "name": "Nombre",
            "platform": "Plataforma",
            "source_url": "URL de origen",
            "external_entity_id": "Identificador externo",
            "country_code": "País (ISO-2)",
            "enabled": "Habilitada",
            "schedule_enabled": "Incluir en la programación",
            "request_delay_seconds": "Espera entre solicitudes (segundos)",
            "timeout_seconds": "Tiempo máximo (segundos)",
            "retry_limit": "Límite de reintentos",
            "max_pages": "Máximo de páginas",
            "max_reviews": "Máximo de reseñas",
            "review_window": "Ventana de reseñas",
            "adapter_config": "Configuración del adaptador (JSON)",
        }
        widgets = {"adapter_config": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["adapter_key"].choices = [(key, key) for key in review_adapter_keys()]
        self.fields["provider"].queryset = Provider.objects.filter(
            data_scope=Provider.DataScope.REAL
        )


class ReviewFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Buscar")
    preset = forms.ChoiceField(required=False, label="Vista", choices=())
    period = forms.TypedChoiceField(
        required=False,
        label="Periodo",
        coerce=int,
        empty_value=6,
        choices=((3, "Últimos 3 meses"), (6, "Últimos 6 meses"), (12, "Últimos 12 meses")),
    )
    provider = forms.MultipleChoiceField(
        required=False,
        label="Competidores",
        choices=(),
        widget=forms.SelectMultiple(attrs={"size": 4}),
    )
    plataforma = forms.ChoiceField(
        required=False, choices=(("", "Todas"), *ReviewSource.Platform.choices)
    )
    pais = forms.CharField(required=False, max_length=2)
    estrellas = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=None,
        choices=(("", "Todas"), *((str(value), str(value)) for value in range(1, 6))),
    )
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    respuesta = forms.ChoiceField(
        required=False,
        choices=(("", "Cualquiera"), ("true", "Con respuesta"), ("false", "Sin respuesta")),
    )
    sentimiento = forms.CharField(required=False)

    def __init__(self, *args, presets=(), providers=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preset"].choices = [
            (preset.slug, f"{preset.name}{' · DEMO' if preset.data_scope == 'demo' else ''}")
            for preset in presets
        ]
        self.fields["provider"].choices = [(provider.code, provider.name) for provider in providers]
