from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from inventario.models import Prenda, tarifa_venta_por_gramo

from .models import DetalleVenta, Venta


@transaction.atomic
def registrar_venta(empleado, articulos, cliente=None):
    articulos = list(articulos)
    if not articulos:
        raise ValidationError("La venta debe incluir al menos una prenda.")

    ids = [int(articulo["prenda_id"]) for articulo in articulos]
    if len(ids) != len(set(ids)):
        raise ValidationError("No se puede incluir la misma prenda más de una vez.")

    prendas = list(
        Prenda.objects.select_for_update()
        .select_related("tipo_oro")
        .filter(pk__in=ids)
        .order_by("pk")
    )
    por_id = {prenda.pk: prenda for prenda in prendas}
    if len(por_id) != len(ids):
        raise ValidationError("Una prenda seleccionada ya no existe.")
    if any(prenda.estado != Prenda.Estado.DISPONIBLE for prenda in prendas):
        raise ValidationError("Una o más prendas ya no están disponibles.")
    if any(tarifa_venta_por_gramo(prenda.tipo_oro) is None for prenda in prendas):
        raise ValidationError(
            "Solo se pueden vender prendas de oro Italiano o Nacional."
        )

    precios = {}
    for articulo in articulos:
        prenda_id = int(articulo["prenda_id"])
        precio = Decimal(str(articulo["precio_final"]))
        if precio <= 0:
            raise ValidationError("El precio final debe ser mayor que cero.")
        precios[prenda_id] = precio

    actualizadas = Prenda.objects.filter(
        pk__in=ids, estado=Prenda.Estado.DISPONIBLE
    ).update(estado=Prenda.Estado.VENDIDA)
    if actualizadas != len(ids):
        raise ValidationError("Una o más prendas fueron vendidas en otra operación.")

    total = sum(precios.values(), Decimal("0.00"))
    venta = Venta.objects.create(empleado=empleado, cliente=cliente, total=total)
    DetalleVenta.objects.bulk_create(
        [
            DetalleVenta(
                venta=venta,
                prenda=por_id[prenda_id],
                precio_final=precios[prenda_id],
            )
            for prenda_id in ids
        ]
    )
    return venta
