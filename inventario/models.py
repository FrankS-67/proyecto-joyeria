from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction


TIPOS_ORO_VENDIBLES = ("Italiano", "Nacional")
TARIFAS_VENTA_POR_GRAMO = {
    "italiano": Decimal("350000.00"),
    "nacional": Decimal("330000.00"),
}


def tarifa_venta_por_gramo(tipo_oro):
    nombre = getattr(tipo_oro, "nombre", tipo_oro)
    if nombre is None:
        return None
    return TARIFAS_VENTA_POR_GRAMO.get(str(nombre).strip().casefold())


def calcular_precio_venta(tipo_oro, peso_gramos):
    tarifa = tarifa_venta_por_gramo(tipo_oro)
    if tarifa is None or peso_gramos is None:
        return None
    return (
        Decimal(str(peso_gramos)) * tarifa
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TipoOro(models.Model):
    nombre = models.CharField("nombre", max_length=50, unique=True)
    pureza = models.DecimalField(
        "pureza (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    valor_gramo = models.DecimalField(
        "valor por gramo", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    valor_prestamo_gramo = models.DecimalField(
        "tarifa de préstamo por gramo",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    precio_compra_gramo = models.DecimalField(
        "tarifa de compra por gramo",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
    )
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "tipo de oro"
        verbose_name_plural = "tipos de oro"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        with transaction.atomic():
            valor_anterior = None
            if self.pk:
                valor_anterior = type(self).objects.filter(pk=self.pk).values_list(
                    "valor_gramo", flat=True
                ).first()
            super().save(*args, **kwargs)
            valor_guardado = type(self).objects.values_list(
                "valor_gramo", flat=True
            ).get(pk=self.pk)
            if valor_anterior is not None and valor_anterior != valor_guardado:
                HistorialPrecioOro.objects.create(
                    tipo_oro=self,
                    valor_gramo=valor_guardado,
                )


class CotizacionOro(models.Model):
    precio_24k_gramo_cop = models.DecimalField(
        "precio internacional 24k por gramo (COP)",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    fecha_cotizacion = models.DateTimeField("fecha de la cotización")
    registrada = models.DateTimeField("registrada", auto_now_add=True)
    fuente = models.CharField("fuente", max_length=80, default="GoldAPI.io")

    class Meta:
        ordering = ["-fecha_cotizacion", "-pk"]
        verbose_name = "cotización internacional del oro"
        verbose_name_plural = "cotizaciones internacionales del oro"

    def __str__(self):
        return f"{self.precio_24k_gramo_cop} COP/g ({self.fecha_cotizacion:%d/%m/%Y %H:%M})"


class HistorialPrecioOro(models.Model):
    tipo_oro = models.ForeignKey(
        TipoOro, on_delete=models.PROTECT, related_name="historial_precios",
        verbose_name="tipo de oro",
    )
    valor_gramo = models.DecimalField(
        "valor por gramo", max_digits=14, decimal_places=2,
    )
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="registrado por",
    )

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "historial de precio del oro"
        verbose_name_plural = "historial de precios del oro"

    def __str__(self):
        return f"{self.tipo_oro}: {self.valor_gramo} ({self.fecha:%d/%m/%Y})"


class Categoria(models.Model):
    nombre = models.CharField("nombre", max_length=80, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.nombre


class Prenda(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        VENDIDA = "VENDIDA", "Vendida"

    class Origen(models.TextChoices):
        COMPRA = "COMPRA", "Compra"
        EMPENO_VENCIDO = "EMPENO_VENCIDO", "Empeño vencido"

    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, verbose_name="categoría",
    )
    tipo_oro = models.ForeignKey(
        TipoOro, on_delete=models.PROTECT, verbose_name="tipo de oro",
    )
    peso_gramos = models.DecimalField(
        "peso en gramos", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    descripcion = models.TextField("descripción", blank=True)
    precio_venta = models.DecimalField(
        "precio de venta", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    foto = models.ImageField("foto", upload_to="prendas/", blank=True)
    estado = models.CharField(
        "estado", max_length=12, choices=Estado.choices, default=Estado.DISPONIBLE,
    )
    origen = models.CharField(
        "origen", max_length=20, choices=Origen.choices, default=Origen.COMPRA,
    )
    articulo_origen = models.OneToOneField(
        "empenos.ArticuloEmpeno",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prenda_inventario",
        verbose_name="artículo de empeño de origen",
    )
    fecha_creacion = models.DateTimeField("fecha de creación", auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion", "-pk"]
        verbose_name = "prenda"
        verbose_name_plural = "prendas"

    def __str__(self):
        return f"{self.categoria} de {self.peso_gramos} g ({self.get_estado_display()})"

    @property
    def tarifa_venta_por_gramo(self):
        return tarifa_venta_por_gramo(self.tipo_oro)

    @property
    def descripcion_catalogo(self):
        return f"{self.peso_gramos} g · Oro {self.tipo_oro}"

    def save(self, *args, **kwargs):
        if self.tipo_oro_id and self.peso_gramos is not None:
            precio = calcular_precio_venta(self.tipo_oro, self.peso_gramos)
            if precio is not None:
                self.precio_venta = precio
                campos_actualizados = kwargs.get("update_fields")
                if campos_actualizados is not None:
                    kwargs["update_fields"] = set(campos_actualizados) | {
                        "precio_venta"
                    }
        super().save(*args, **kwargs)
