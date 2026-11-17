from django.core.management.base import BaseCommand, CommandError

from inventario.servicios import (
    ErrorCotizacionOro,
    actualizar_precios_oro,
    obtener_cotizacion_oro,
)


class Command(BaseCommand):
    help = "Consulta la cotización del oro y actualiza las tarifas de compra."

    def handle(self, *args, **options):
        try:
            cotizacion = obtener_cotizacion_oro()
            registro = actualizar_precios_oro(cotizacion)
        except ErrorCotizacionOro as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Precios actualizados. "
                f"Referencia 24k: ${registro.precio_24k_gramo_cop:,.2f} COP/g; "
                f"cotización del {registro.fecha_cotizacion:%d/%m/%Y %H:%M} UTC."
            )
        )
