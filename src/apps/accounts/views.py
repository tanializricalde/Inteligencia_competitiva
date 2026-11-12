from django.contrib.auth import views as auth_views

from apps.market.branding import get_application_branding


class ApplicationPasswordResetView(auth_views.PasswordResetView):
    def dispatch(self, request, *args, **kwargs):
        self.extra_email_context = {
            "application_name": get_application_branding(request).application_name
        }
        return super().dispatch(request, *args, **kwargs)
