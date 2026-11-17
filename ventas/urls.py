from django.urls import path

from .views import VentaCrearView, VentaListaView

app_name = "ventas"

urlpatterns = [
    path("", VentaListaView.as_view(), name="lista"),
    path("nueva/", VentaCrearView.as_view(), name="nueva"),
]
