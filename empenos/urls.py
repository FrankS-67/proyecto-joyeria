from django.urls import path
from .views import (
    ClienteCrearView,
    ClienteEditarView,
    ClienteListaView,
    ContratoCrearView,
    ContratoDetalleView,
    ContratoAnularView,
    ContratoLiquidarView,
    ContratoImprimirView,
    ContratoListaView,
    ContratoPagoView,
    SimuladorEmpenoView,
)


app_name = "empenos"

urlpatterns = [
    path("simulador/", SimuladorEmpenoView.as_view(), name="simulador"),
    path("clientes/", ClienteListaView.as_view(), name="cliente_list"),
    path("clientes/nuevo/", ClienteCrearView.as_view(), name="cliente_crear"),
    path("clientes/<int:pk>/editar/", ClienteEditarView.as_view(), name="cliente_editar"),
    path("contratos/", ContratoListaView.as_view(), name="contrato_list"),
    path("contratos/nuevo/", ContratoCrearView.as_view(), name="contrato_crear"),
    path("contratos/<int:numero>/", ContratoDetalleView.as_view(), name="contrato_detalle"),
    path("contratos/<int:numero>/pago/", ContratoPagoView.as_view(), name="contrato_pago"),
    path("contratos/<int:numero>/anular/", ContratoAnularView.as_view(), name="contrato_anular"),
    path(
        "contratos/<int:numero>/liquidar/",
        ContratoLiquidarView.as_view(),
        name="contrato_liquidar",
    ),
    path(
        "contratos/<int:numero>/imprimir/",
        ContratoImprimirView.as_view(),
        name="contrato_imprimir",
    ),
]
