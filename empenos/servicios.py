import calendar
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from inventario.models import Prenda, TipoOro, calcular_precio_venta

from .models import ArticuloEmpeno, Cliente, Contrato, Pago, RangoInteres


PESO = Decimal("1")
TASA_MORA_MENSUAL = Decimal("0.5")
PRESTAMO_MINIMO = Decimal("50000")


def _sumar_meses(fecha, meses):
    mes_indice = fecha.month - 1 + meses
    anio = fecha.year + mes_indice // 12
    mes = mes_indice % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


def fecha_liquidacion(contrato):
    return _sumar_meses(
        contrato.fecha_vencimiento, settings.PERIODO_GRACIA_MESES
    )


def _periodos_transcurridos(inicio, fin):
    if fin <= inicio:
        return Decimal("0")

    meses = (fin.year - inicio.year) * 12 + fin.month - inicio.month
    aniversario = _sumar_meses(inicio, meses)
    if aniversario > fin:
        meses -= 1
        aniversario = _sumar_meses(inicio, meses)

    dias_restantes = (fin - aniversario).days
    fraccion = Decimal("0")
    if dias_restantes:
        fraccion = Decimal("0.5") if dias_restantes <= 15 else Decimal("1")
    return Decimal(meses) + fraccion


def _redondear_peso(valor):
    return valor.quantize(PESO, rounding=ROUND_CEILING)


def _calcular_interes_tramo(capital, tasa_mensual, inicio, vencimiento, fecha):
    periodos = _periodos_transcurridos(inicio, fecha)
    periodos_mora = _periodos_transcurridos(vencimiento, fecha)
    tasa = tasa_mensual + TASA_MORA_MENSUAL * periodos_mora
    interes = capital * (tasa / Decimal("100")) * periodos
    return _redondear_peso(interes)


def calcular_valor_empeno(articulos):
    total = Decimal("0.00")
    for articulo in articulos:
        if isinstance(articulo, dict):
            peso = Decimal(str(articulo.get("peso_gramos")))
            tipo_oro = articulo.get("tipo_oro")
            if not isinstance(tipo_oro, TipoOro):
                tipo_oro = TipoOro.objects.get(pk=tipo_oro)
            valor_gramo = tipo_oro.valor_prestamo_gramo
        else:
            peso = articulo.peso_gramos
            valor_gramo = articulo.valor_gramo_aplicado
        if valor_gramo <= 0:
            raise ValidationError(
                "No hay una tarifa de préstamo por gramo configurada para este tipo de oro."
            )
        total += Decimal(str(peso)) * valor_gramo
    return total


def redondear_miles_hacia_abajo(valor):
    return valor.quantize(Decimal("1E3"), rounding=ROUND_DOWN)


def tasa_para_monto(monto):
    monto = Decimal(str(monto))
    rangos = RangoInteres.objects.filter(monto_desde__lte=monto).filter(
        Q(monto_hasta__isnull=True) | Q(monto_hasta__gte=monto)
    )
    rango = rangos.order_by("monto_desde").first()
    if rango is None:
        raise ValidationError("No hay un rango de interés configurado para este monto.")
    return rango.tasa_mensual


def _estado_financiero(contrato, fecha):
    if contrato.estado in {Contrato.Estado.LIQUIDADO, Contrato.Estado.ANULADO}:
        return Decimal("0"), Decimal("0")

    capital = contrato.valor_prestamo
    interes_pendiente = Decimal("0")
    inicio_tramo = contrato.fecha_inicio
    vencimiento = contrato.fecha_vencimiento
    pagos = contrato.pagos.filter(
        tipo__in=[Pago.Tipo.ABONO, Pago.Tipo.RENOVACION, Pago.Tipo.RETIRO],
        fecha__date__lte=fecha,
    ).order_by("fecha", "pk")

    for pago in pagos:
        fecha_pago = timezone.localtime(pago.fecha).date()
        if fecha_pago < inicio_tramo:
            continue
        interes_pendiente += _calcular_interes_tramo(
            capital,
            contrato.tasa_aplicada,
            inicio_tramo,
            vencimiento,
            fecha_pago,
        )
        inicio_tramo = fecha_pago
        if pago.tipo == Pago.Tipo.RENOVACION:
            interes_pendiente = max(Decimal("0"), interes_pendiente - pago.monto)
            vencimiento = _sumar_meses(
                vencimiento, settings.PLAZO_CONTRATO_MESES
            )
        elif pago.tipo == Pago.Tipo.RETIRO:
            capital = Decimal("0")
            interes_pendiente = Decimal("0")
        else:
            aplicado_interes = min(interes_pendiente, pago.monto)
            interes_pendiente -= aplicado_interes
            capital = max(Decimal("0"), capital - (pago.monto - aplicado_interes))

    if fecha >= inicio_tramo:
        interes_pendiente += _calcular_interes_tramo(
            capital,
            contrato.tasa_aplicada,
            inicio_tramo,
            vencimiento,
            fecha,
        )
    return capital, interes_pendiente


def calcular_interes(contrato, fecha=None):
    fecha = fecha or timezone.localdate()
    return _estado_financiero(contrato, fecha)[1]


def calcular_saldo(contrato, fecha=None):
    fecha = fecha or timezone.localdate()
    capital, interes = _estado_financiero(contrato, fecha)
    return capital + interes


def _validar_prestamo(monto, valor_maximo):
    if valor_maximo < PRESTAMO_MINIMO:
        raise ValidationError(
            "El valor calculado no alcanza el préstamo mínimo de $ 50.000."
        )
    if monto < PRESTAMO_MINIMO:
        raise ValidationError("El préstamo mínimo permitido es de $ 50.000.")
    if monto > valor_maximo:
        raise ValidationError(
            "El préstamo no puede superar el valor calculado disponible "
            f"({valor_maximo})."
        )


def simular_empeno(articulos, valor_prestamo, fecha_inicio=None):
    articulos = list(articulos)
    if not articulos:
        raise ValidationError("Agrega al menos un artículo para simular el empeño.")

    valor_prestamo = Decimal(str(valor_prestamo))
    if not valor_prestamo.is_finite():
        raise ValidationError("El valor del préstamo no es válido.")

    fecha_inicio = fecha_inicio or timezone.localdate()
    fecha_vencimiento = _sumar_meses(
        fecha_inicio, settings.PLAZO_CONTRATO_MESES
    )
    valor_calculado = calcular_valor_empeno(articulos)
    valor_maximo_prestable = redondear_miles_hacia_abajo(valor_calculado)
    _validar_prestamo(valor_prestamo, valor_maximo_prestable)
    tasa = tasa_para_monto(valor_prestamo)

    articulos_detalle = []
    for articulo in articulos:
        tipo = articulo["tipo_oro"]
        peso = Decimal(str(articulo["peso_gramos"]))
        valor_gramo = tipo.valor_prestamo_gramo
        articulos_detalle.append(
            {
                "categoria": articulo["categoria"],
                "tipo_oro": tipo,
                "peso_gramos": peso,
                "valor_gramo": valor_gramo,
                "valor_calculado": peso * valor_gramo,
            }
        )

    proyecciones = []
    for mes in range(1, settings.PLAZO_CONTRATO_MESES + 1):
        fecha = _sumar_meses(fecha_inicio, mes)
        interes = _calcular_interes_tramo(
            valor_prestamo, tasa, fecha_inicio, fecha_vencimiento, fecha
        )
        proyecciones.append(
            {
                "periodo": f"Mes {mes}",
                "fecha": fecha,
                "tasa": tasa,
                "interes": interes,
                "saldo": valor_prestamo + interes,
            }
        )

    for mes_mora in range(1, settings.PERIODO_GRACIA_MESES + 1):
        fecha = _sumar_meses(fecha_vencimiento, mes_mora)
        tasa_mora = tasa + TASA_MORA_MENSUAL * mes_mora
        interes = _calcular_interes_tramo(
            valor_prestamo, tasa, fecha_inicio, fecha_vencimiento, fecha
        )
        proyecciones.append(
            {
                "periodo": f"Mora {mes_mora}",
                "fecha": fecha,
                "tasa": tasa_mora,
                "interes": interes,
                "saldo": valor_prestamo + interes,
            }
        )

    return {
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_liquidacion": _sumar_meses(
            fecha_vencimiento, settings.PERIODO_GRACIA_MESES
        ),
        "articulos": articulos_detalle,
        "valor_calculado_total": valor_calculado,
        "valor_maximo_prestable": valor_maximo_prestable,
        "valor_prestamo": valor_prestamo,
        "tasa_mensual": tasa,
        "proyecciones": proyecciones,
    }


def crear_contrato(datos_contrato, articulos, empleado):
    articulos = list(articulos)
    if not articulos:
        raise ValidationError("El contrato debe incluir al menos un artículo.")

    fecha_inicio = datos_contrato.get("fecha_inicio") or timezone.localdate()
    fecha_esperada = _sumar_meses(fecha_inicio, settings.PLAZO_CONTRATO_MESES)
    fecha_vencimiento = datos_contrato.get("fecha_vencimiento")
    if not fecha_vencimiento:
        fecha_vencimiento = fecha_esperada
    if fecha_vencimiento != fecha_esperada:
        raise ValidationError("El contrato debe tener un plazo inicial de cuatro meses.")

    cliente = datos_contrato.get("cliente")
    if not isinstance(cliente, Cliente):
        raise ValidationError("Debe seleccionar o registrar un cliente.")

    valor_prestamo = Decimal(str(datos_contrato["valor_prestamo"]))
    with transaction.atomic():
        ids_tipos = {
            articulo["tipo_oro"].pk
            if isinstance(articulo.get("tipo_oro"), TipoOro)
            else int(articulo["tipo_oro"])
            for articulo in articulos
        }
        tipos = {
            tipo.pk: tipo
            for tipo in TipoOro.objects.select_for_update().filter(pk__in=ids_tipos)
        }
        if len(tipos) != len(ids_tipos):
            raise ValidationError("Uno de los tipos de oro seleccionados ya no existe.")
        articulos_con_precios = [
            {
                **articulo,
                "tipo_oro": tipos[
                    articulo["tipo_oro"].pk
                    if isinstance(articulo.get("tipo_oro"), TipoOro)
                    else int(articulo["tipo_oro"])
                ],
            }
            for articulo in articulos
        ]
        valor_calculado = calcular_valor_empeno(articulos_con_precios)
        valor_maximo_prestable = redondear_miles_hacia_abajo(valor_calculado)
        _validar_prestamo(valor_prestamo, valor_maximo_prestable)
        tasa = tasa_para_monto(valor_prestamo)
        for intento in range(3):
            numero = (Contrato.objects.aggregate(maximo=Max("numero"))["maximo"] or 0) + 1
            try:
                with transaction.atomic():
                    contrato = Contrato.objects.create(
                        numero=numero,
                        cliente=cliente,
                        empleado=empleado,
                        fecha_inicio=fecha_inicio,
                        fecha_vencimiento=fecha_vencimiento,
                        valor_prestamo=valor_prestamo,
                        tasa_aplicada=tasa,
                        observaciones=datos_contrato.get("observaciones", ""),
                        estado=Contrato.Estado.ACTIVO,
                    )
                    for articulo in articulos_con_precios:
                        tipo = articulo["tipo_oro"]
                        ArticuloEmpeno.objects.create(
                            contrato=contrato,
                            categoria=articulo["categoria"],
                            tipo_oro=tipo,
                            peso_gramos=articulo["peso_gramos"],
                            valor_gramo_aplicado=tipo.valor_prestamo_gramo,
                            descripcion=articulo.get("descripcion", ""),
                        )
                    return contrato
            except IntegrityError:
                if intento == 2:
                    raise


@transaction.atomic
def registrar_pago(contrato, monto, tipo, empleado, observaciones=""):
    contrato = Contrato.objects.select_for_update().get(pk=contrato.pk)
    if contrato.estado != Contrato.Estado.ACTIVO:
        raise ValidationError("Solo se pueden registrar pagos en contratos activos.")

    monto = Decimal(str(monto))
    if monto <= 0:
        raise ValidationError("El monto debe ser mayor que cero.")
    hoy = timezone.localdate()

    if tipo == Pago.Tipo.ABONO:
        if monto > calcular_saldo(contrato, hoy):
            raise ValidationError("El abono no puede superar el saldo total.")
        return Pago.objects.create(
            contrato=contrato,
            monto=monto,
            tipo=tipo,
            empleado=empleado,
            observaciones=observaciones,
        )

    interes = calcular_interes(contrato, hoy)
    if tipo == Pago.Tipo.RENOVACION:
        if monto != interes:
            raise ValidationError(
                f"El valor de renovación debe ser el interés acumulado: {interes}."
            )
        pago = Pago.objects.create(
            contrato=contrato,
            monto=monto,
            tipo=tipo,
            empleado=empleado,
            observaciones=observaciones,
        )
        contrato.fecha_vencimiento = _sumar_meses(
            contrato.fecha_vencimiento, settings.PLAZO_CONTRATO_MESES
        )
        contrato.save(update_fields=["fecha_vencimiento"])
        return pago

    if tipo == Pago.Tipo.RETIRO:
        saldo = calcular_saldo(contrato, hoy)
        if monto != saldo:
            raise ValidationError(f"El valor de retiro debe ser el saldo total: {saldo}.")
        pago = Pago.objects.create(
            contrato=contrato,
            monto=monto,
            tipo=tipo,
            empleado=empleado,
            observaciones=observaciones,
        )
        contrato.estado = Contrato.Estado.RETIRADO
        contrato.save(update_fields=["estado"])
        return pago

    raise ValidationError("Tipo de pago no válido.")


@transaction.atomic
def pasar_a_inventario(contrato, empleado, precios_venta=None):
    contrato = Contrato.objects.select_for_update().get(pk=contrato.pk)
    hoy = timezone.localdate()
    disponible_desde = fecha_liquidacion(contrato)
    if contrato.estado != Contrato.Estado.ACTIVO:
        raise ValidationError("Solo se pueden liquidar contratos activos.")
    if hoy < disponible_desde:
        raise ValidationError(
            f"El contrato solo se puede liquidar desde el {disponible_desde:%d/%m/%Y}."
        )

    articulos = list(
        contrato.articulos.select_related("categoria", "tipo_oro").order_by("pk")
    )
    if not articulos:
        raise ValidationError("No se puede liquidar un contrato sin artículos.")
    ids_articulos = {articulo.pk for articulo in articulos}
    if precios_venta is None:
        raise ValidationError(
            "Debe indicar un precio de venta inicial para cada artículo."
        )
    if set(precios_venta) != ids_articulos:
        raise ValidationError("Debe indicar un precio para cada artículo del contrato.")

    prendas = []
    for articulo in articulos:
        precio = calcular_precio_venta(
            articulo.tipo_oro, articulo.peso_gramos
        )
        if precio is None:
            precio = Decimal(str(precios_venta[articulo.pk]))
        if precio <= 0:
            raise ValidationError("El precio de venta debe ser mayor que cero.")
        prendas.append(
            Prenda(
                categoria=articulo.categoria,
                tipo_oro=articulo.tipo_oro,
                peso_gramos=articulo.peso_gramos,
                descripcion=articulo.descripcion,
                precio_venta=precio,
                estado=Prenda.Estado.DISPONIBLE,
                origen=Prenda.Origen.EMPENO_VENCIDO,
                articulo_origen=articulo,
            )
        )

    Prenda.objects.bulk_create(prendas)
    contrato.estado = Contrato.Estado.LIQUIDADO
    nota_liquidacion = (
        f"Liquidado por {empleado.get_username()} "
        f"el {hoy:%d/%m/%Y} después del periodo de gracia."
    )
    contrato.observaciones = "\n".join(
        parte for parte in (contrato.observaciones, nota_liquidacion) if parte
    )
    contrato.save(update_fields=["estado", "observaciones"])
    return list(
        Prenda.objects.filter(articulo_origen__contrato=contrato).order_by(
            "articulo_origen_id"
        )
    )


@transaction.atomic
def anular_contrato(contrato, empleado, observacion=""):
    contrato = Contrato.objects.select_for_update().get(pk=contrato.pk)
    if contrato.estado == Contrato.Estado.ANULADO:
        raise ValidationError("El contrato ya está anulado.")
    observacion = (observacion or "").strip()
    if not observacion:
        raise ValidationError("La observación de anulación es obligatoria.")

    hoy = timezone.localdate()
    nota_anulacion = (
        f"Anulado por {empleado.get_username()} el {hoy:%d/%m/%Y}: {observacion}"
    )
    contrato.observaciones = "\n".join(
        parte for parte in (contrato.observaciones, nota_anulacion) if parte
    )
    contrato.estado = Contrato.Estado.ANULADO
    contrato.save(update_fields=["estado", "observaciones"])
