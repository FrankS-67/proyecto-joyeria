from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ("prenda", "precio_final")


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "cliente", "empleado", "total")
    list_filter = ("fecha",)
    search_fields = ("cliente__documento", "cliente__nombres")
    inlines = (DetalleVentaInline,)
