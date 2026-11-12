from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.scraping.models import ScrapeSource

from .branding import get_application_branding


@require_POST
@login_required
@permission_required("scraping.change_scrapesource", raise_exception=True)
def toggle_source(request, source_id: int):
    source = get_object_or_404(ScrapeSource, pk=source_id)
    source.is_active = not source.is_active
    source.save(update_fields=("is_active",))
    messages.success(request, f"Fuente {'activada' if source.is_active else 'desactivada'}.")
    return redirect("sources")


@require_POST
@login_required
@permission_required("notifications.change_notificationrecipient", raise_exception=True)
def test_email_configuration(request):
    try:
        message = EmailMultiAlternatives(
            f"[{get_application_branding(request).application_name}] Prueba de correo",
            "La configuración de correo funciona correctamente.",
            to=[request.user.email],
        )
        message.attach_alternative(
            "<p>La configuración de correo funciona correctamente.</p>", "text/html"
        )
        message.send(fail_silently=False)
    except Exception as exc:
        messages.error(request, f"No fue posible enviar la prueba ({type(exc).__name__}).")
    else:
        messages.success(request, "Correo de prueba enviado.")
    return redirect("functional_settings")
