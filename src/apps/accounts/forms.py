from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)

from apps.form_styling import StyledFormMixin


class EmailAuthenticationForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    error_messages = {
        "invalid_login": "No fue posible iniciar sesión con esos datos.",
        "inactive": "No fue posible iniciar sesión con esos datos.",
    }


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass
