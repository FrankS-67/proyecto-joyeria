from django.urls import path
from .views import HomeView, MiCuentaView, RegistroClienteView, ReporteView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("cuenta/registro/", RegistroClienteView.as_view(), name="registro_cliente"),
    path("mi-cuenta/", MiCuentaView.as_view(), name="mi_cuenta"),
    path("reportes/", ReporteView.as_view(), name="reportes"),
]
