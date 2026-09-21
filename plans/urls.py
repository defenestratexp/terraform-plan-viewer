"""URL configuration for plans app."""
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("plan/<path:plan_id>/approve/", views.approve_plan, name="approve_plan"),
    path("plan/<path:plan_id>/", views.plan_detail, name="plan_detail"),
    path("health/", views.health_check, name="health"),
]
