from django.contrib import admin

from .models import Cliente, RangoInteres


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("documento", "nombres", "telefono", "usuario", "creado")
    search_fields = ("documento", "nombres")


@admin.register(RangoInteres)
class RangoInteresAdmin(admin.ModelAdmin):
    list_display = ("monto_desde", "monto_hasta", "tasa_mensual")
