from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from decimal import Decimal

from empenos.models import Cliente
from inventario.models import Prenda


class Venta(models.Model):
    empleado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ventas_registradas",
        verbose_name="empleado",
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ventas",
        verbose_name="cliente",
    )
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    total = models.DecimalField(
        "total",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "venta"
        verbose_name_plural = "ventas"

    def __str__(self):
        return f"Venta {self.pk or 'nueva'}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        related_name="detalles",
        verbose_name="venta",
    )
    prenda = models.ForeignKey(
        Prenda,
        on_delete=models.PROTECT,
        related_name="detalles_venta",
        verbose_name="prenda",
    )
    precio_final = models.DecimalField(
        "precio final",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"
        constraints = [
            models.UniqueConstraint(fields=["prenda"], name="venta_prenda_unica"),
        ]

    def __str__(self):
        return f"{self.prenda} - {self.precio_final}"
