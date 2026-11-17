import json
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import CotizacionOro, TipoOro

PORCENTAJE_COMPRA = Decimal("0.95")
URL_COTIZACION = "https://www.goldapi.io/api/price/XAU/COP"


class ErrorCotizacionOro(Exception):
    pass


@dataclass(frozen=True)
class CotizacionMercado:
    precio_24k_gramo_cop: Decimal
    fecha_cotizacion: datetime


def obtener_cotizacion_oro():
    token = settings.GOLDAPI_TOKEN
    if not token:
        raise ErrorCotizacionOro(
            "Configura GOLDAPI_TOKEN para consultar la cotización del oro."
        )

    solicitud = Request(
        URL_COTIZACION,
        headers={"x-access-token": token, "Accept": "application/json"},
    )
    try:
        with urlopen(solicitud, timeout=10) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except HTTPError as error:
        raise ErrorCotizacionOro(
            f"GoldAPI.io respondió con el estado HTTP {error.code}."
        ) from error
    except (URLError, TimeoutError) as error:
        raise ErrorCotizacionOro(
            "No fue posible conectar con GoldAPI.io."
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ErrorCotizacionOro(
            "GoldAPI.io devolvió una respuesta que no es JSON válido."
        ) from error

    try:
        precio_por_gramo = Decimal(str(datos["price_per_unit"]["gram"]))
        fecha_cotizacion = datetime.fromtimestamp(
            int(datos["timestamp"]), tz=datetime_timezone.utc
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError, InvalidOperation) as error:
        raise ErrorCotizacionOro(
            "La respuesta de GoldAPI.io no contiene una cotización válida."
        ) from error

    if not precio_por_gramo.is_finite() or precio_por_gramo <= 0:
        raise ErrorCotizacionOro(
            "GoldAPI.io devolvió un precio por gramo inválido."
        )

    return CotizacionMercado(precio_por_gramo, fecha_cotizacion)


def actualizar_precios_oro(cotizacion):
    with transaction.atomic():
        registro = CotizacionOro.objects.create(
            precio_24k_gramo_cop=cotizacion.precio_24k_gramo_cop,
            fecha_cotizacion=cotizacion.fecha_cotizacion,
        )
        for tipo in TipoOro.objects.select_for_update():
            valor_referencial = (
                cotizacion.precio_24k_gramo_cop
                * tipo.pureza
                / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            tipo.valor_gramo = valor_referencial
            tipo.precio_compra_gramo = (
                valor_referencial * PORCENTAJE_COMPRA
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            tipo.save(
                update_fields=[
                    "valor_gramo",
                    "precio_compra_gramo",
                    "actualizado",
                ]
            )
    return registro
