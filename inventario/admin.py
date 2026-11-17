from django.contrib import admin

from .forms import PrendaForm
from .models import Categoria, CotizacionOro, HistorialPrecioOro, Prenda, TipoOro


@admin.register(TipoOro)
class TipoOroAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "pureza",
        "valor_gramo",
        "valor_prestamo_gramo",
        "precio_compra_gramo",
        "actualizado",
    )
    search_fields = ("nombre",)


@admin.register(HistorialPrecioOro)
class HistorialPrecioOroAdmin(admin.ModelAdmin):
    list_display = ("tipo_oro", "valor_gramo", "fecha", "registrado_por")
    list_filter = ("tipo_oro",)
    readonly_fields = ("fecha",)


@admin.register(CotizacionOro)
class CotizacionOroAdmin(admin.ModelAdmin):
    list_display = ("precio_24k_gramo_cop", "fecha_cotizacion", "registrada", "fuente")
    readonly_fields = ("precio_24k_gramo_cop", "fecha_cotizacion", "registrada", "fuente")


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)


@admin.register(Prenda)
class PrendaAdmin(admin.ModelAdmin):
    form = PrendaForm
    list_display = ("categoria", "tipo_oro", "peso_gramos", "precio_venta", "estado")
    list_filter = ("estado", "origen", "tipo_oro", "categoria")
    search_fields = ("descripcion",)
