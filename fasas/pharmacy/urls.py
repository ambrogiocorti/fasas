from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import DrugForm, DrugInteractionForm
from .models import Drug, DrugInteraction

app_name = "pharmacy"

urlpatterns = [
    path("", views.stock, name="stock"),
    path("carico/", views.lot_load, name="lot_load"),
    path("lotto/<int:pk>/", views.lot_detail, name="lot_detail"),
] + config_urls(
    "farmaci", "drug", Drug, DrugForm,
    ("name", "active_ingredient", "atc_code", "form", "strength", "min_stock", "active"),
    search_fields=("name", "active_ingredient", "atc_code"), namespace="pharmacy",
) + config_urls(
    "interazioni", "interaction", DrugInteraction, DrugInteractionForm,
    ("ingredient_a", "ingredient_b", "severity", "description"),
    search_fields=("ingredient_a", "ingredient_b"), namespace="pharmacy",
)
