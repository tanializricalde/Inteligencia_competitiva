from django.urls import path

from . import views

app_name = "pipeline"

urlpatterns = [
    path("api/features-wide/", views.features_wide, name="features-wide"),
]
