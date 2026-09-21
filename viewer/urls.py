"""URL configuration for terraform-viewer project."""
from django.urls import path, include

urlpatterns = [
    path("", include("plans.urls")),
]
