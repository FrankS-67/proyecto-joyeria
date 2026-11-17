from django.urls import path

from .views import (
    CatalogoDetalleView,
    CatalogoListaView,
    PrendaCrearView,
    PrendaEditarView,
    PrendaEliminarView,
    PrendaGestionListaView,
)

app_name = "inventario"

urlpatterns = [
    path("", CatalogoListaView.as_view(), name="catalogo"),
    path("gestion/", PrendaGestionListaView.as_view(), name="gestion_lista"),
    path("gestion/nueva/", PrendaCrearView.as_view(), name="prenda_crear"),
    path("gestion/<int:pk>/editar/", PrendaEditarView.as_view(), name="prenda_editar"),
    path("gestion/<int:pk>/eliminar/", PrendaEliminarView.as_view(), name="prenda_eliminar"),
    path("<int:pk>/", CatalogoDetalleView.as_view(), name="prenda_detalle"),
]
