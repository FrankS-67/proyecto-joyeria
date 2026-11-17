from decimal import Decimal
from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import ArticuloEmpeno, Cliente, Contrato, Pago, RangoInteres
from .servicios import (
    anular_contrato,
    calcular_valor_empeno,
    calcular_interes,
    calcular_saldo,
    crear_contrato,
    registrar_pago,
    pasar_a_inventario,
    redondear_miles_hacia_abajo,
    simular_empeno,
    tasa_para_monto,
    _sumar_meses,
)
from inventario.models import Categoria, HistorialPrecioOro, Prenda, TipoOro
from django.utils import timezone


class ModelosEmpenosTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="empleado", password="clave")
        self.cliente = Cliente.objects.create(
            documento="123", nombres="Persona Demo", telefono="3000000000"
        )
        self.tipo_oro = TipoOro.objects.create(
            nombre="Nacional", valor_gramo=Decimal("100.00")
        )
        self.categoria = Categoria.objects.create(nombre="Anillo")

    def test_cambio_de_valor_oro_crea_historial(self):
        self.tipo_oro.valor_gramo = Decimal("125.00")
        self.tipo_oro.save()

        historial = HistorialPrecioOro.objects.get()
        self.assertEqual(historial.valor_gramo, Decimal("125.00"))

    def test_contrato_numero_formateado_y_vencimiento_derivado(self):
        contrato = Contrato.objects.create(
            numero=1,
            cliente=self.cliente,
            empleado=self.usuario,
            fecha_vencimiento=date(2020, 1, 1),
            valor_prestamo=Decimal("100.00"),
            tasa_aplicada=Decimal("5.00"),
        )

        self.assertEqual(contrato.numero_formateado, "000001")
        self.assertTrue(contrato.esta_vencido)

    def test_rango_rechaza_limites_invertidos_y_solapamiento(self):
        rango = RangoInteres.objects.create(
            monto_desde=Decimal("0.00"),
            monto_hasta=Decimal("1000.00"),
            tasa_mensual=Decimal("5.00"),
        )
        with self.assertRaises(ValidationError):
            RangoInteres(
                monto_desde=Decimal("900.00"),
                monto_hasta=Decimal("1200.00"),
                tasa_mensual=Decimal("6.00"),
            ).full_clean()
        with self.assertRaises(ValidationError):
            RangoInteres(
                monto_desde=Decimal("1200.00"),
                monto_hasta=Decimal("1100.00"),
                tasa_mensual=Decimal("6.00"),
            ).full_clean()
        self.assertIsNotNone(rango.pk)


class ServiciosEmpenosTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="empleado_servicio")
        self.cliente = Cliente.objects.create(
            documento="456", nombres="Cliente Servicio", telefono="3000000001"
        )
        self.tipo_oro = TipoOro.objects.create(
            nombre="Italiano",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("300000.00"),
        )
        self.categoria = Categoria.objects.create(nombre="Cadena")
        self.rango = RangoInteres.objects.create(
            monto_desde=Decimal("0.00"),
            monto_hasta=None,
            tasa_mensual=Decimal("5.00"),
        )

    def crear_contrato(self, inicio, vencimiento, prestamo="100000.00"):
        return Contrato.objects.create(
            numero=1,
            cliente=self.cliente,
            empleado=self.usuario,
            fecha_inicio=inicio,
            fecha_vencimiento=vencimiento,
            valor_prestamo=Decimal(prestamo),
            tasa_aplicada=Decimal("5.00"),
        )

    def test_calcular_valor_empeno_usa_tarifa_aplicada_y_decimal(self):
        articulo = ArticuloEmpeno(
            contrato_id=1,
            categoria=self.categoria,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("2.50"),
            valor_gramo_aplicado=Decimal("300000.00"),
        )

        self.assertEqual(
            calcular_valor_empeno([articulo]), Decimal("750000.000000")
        )

    def test_calcular_valor_empeno_aplica_tarifas_fijas_y_redondeo_total(self):
        nacional = TipoOro.objects.create(
            nombre="Nacional cálculo",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("280000.00"),
        )
        catorce_k = TipoOro.objects.create(
            nombre="14k cálculo",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("250000.00"),
        )
        chino = TipoOro.objects.create(
            nombre="Chino cálculo",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("200000.00"),
        )
        articulos = [
            {"tipo_oro": self.tipo_oro, "peso_gramos": Decimal("1.00")},
            {"tipo_oro": nacional, "peso_gramos": Decimal("1.00")},
            {"tipo_oro": catorce_k, "peso_gramos": Decimal("1.01")},
            {"tipo_oro": chino, "peso_gramos": Decimal("1.00")},
        ]

        valor_total = calcular_valor_empeno(articulos)

        self.assertEqual(valor_total, Decimal("1032500.0000"))
        self.assertEqual(
            redondear_miles_hacia_abajo(valor_total),
            Decimal("1032000"),
        )

    def test_tasa_para_monto_acepta_limites_y_sin_tope(self):
        self.assertEqual(tasa_para_monto(Decimal("50000.00")), Decimal("5.00"))
        self.assertEqual(tasa_para_monto(Decimal("99999999.00")), Decimal("5.00"))

    def test_tasa_para_monto_falla_si_no_hay_rango(self):
        RangoInteres.objects.all().delete()
        with self.assertRaises(ValidationError):
            tasa_para_monto(Decimal("100000.00"))

    def test_simulacion_muestra_plazo_y_mora_sin_crear_contrato(self):
        resultado = simular_empeno(
            [
                {
                    "categoria": self.categoria,
                    "tipo_oro": self.tipo_oro,
                    "peso_gramos": Decimal("12.00"),
                }
            ],
            Decimal("100000.00"),
            date(2026, 1, 1),
        )

        self.assertEqual(
            resultado["valor_calculado_total"], Decimal("3600000.0000")
        )
        self.assertEqual(
            resultado["valor_maximo_prestable"], Decimal("3600000")
        )
        self.assertEqual(resultado["fecha_vencimiento"], date(2026, 5, 1))
        self.assertEqual(resultado["fecha_liquidacion"], date(2026, 8, 1))
        self.assertEqual(len(resultado["proyecciones"]), 7)
        self.assertEqual(resultado["proyecciones"][3]["interes"], Decimal("20000"))
        self.assertEqual(resultado["proyecciones"][4]["tasa"], Decimal("5.5"))
        self.assertEqual(resultado["proyecciones"][4]["interes"], Decimal("27500"))
        self.assertEqual(Contrato.objects.count(), 0)

    def test_simulacion_rechaza_prestamo_superior_al_valor_calculado(self):
        with self.assertRaisesRegex(ValidationError, "valor calculado disponible"):
            simular_empeno(
                [
                    {
                        "categoria": self.categoria,
                        "tipo_oro": self.tipo_oro,
                        "peso_gramos": Decimal("12.00"),
                    }
                ],
                Decimal("4000000.00"),
                date(2026, 1, 1),
            )

    def test_crear_contrato_asigna_numero_y_congela_valores(self):
        datos = {
            "cliente": self.cliente,
            "fecha_inicio": date(2026, 1, 1),
            "fecha_vencimiento": date(2026, 5, 1),
            "valor_prestamo": Decimal("100000.00"),
        }
        articulos = [
            {
                "categoria": self.categoria,
                "tipo_oro": self.tipo_oro,
                "peso_gramos": Decimal("6.00"),
                "descripcion": "Primera pieza",
            },
            {
                "categoria": self.categoria,
                "tipo_oro": self.tipo_oro,
                "peso_gramos": Decimal("6.00"),
                "descripcion": "Segunda pieza",
            },
        ]

        contrato = crear_contrato(datos, articulos, self.usuario)
        self.tipo_oro.valor_gramo = Decimal("120000.00")
        self.tipo_oro.valor_prestamo_gramo = Decimal("310000.00")
        self.tipo_oro.save()
        self.rango.tasa_mensual = Decimal("6.00")
        self.rango.save()
        siguiente = crear_contrato(
            {**datos, "fecha_inicio": date(2026, 2, 1), "fecha_vencimiento": date(2026, 6, 1)},
            articulos,
            self.usuario,
        )

        self.assertEqual(contrato.numero, 1)
        self.assertEqual(siguiente.numero, 2)
        self.assertEqual(contrato.articulos.count(), 2)
        self.assertEqual(
            list(contrato.articulos.values_list("valor_gramo_aplicado", flat=True)),
            [Decimal("300000.00"), Decimal("300000.00")],
        )
        self.assertEqual(
            list(siguiente.articulos.values_list("valor_gramo_aplicado", flat=True)),
            [Decimal("310000.00"), Decimal("310000.00")],
        )
        self.assertEqual(contrato.tasa_aplicada, Decimal("5.00"))
        self.assertEqual(siguiente.tasa_aplicada, Decimal("6.00"))

    def test_crear_contrato_exige_plazo_confirmado_de_cuatro_meses(self):
        with self.assertRaises(ValidationError):
            crear_contrato(
                {
                    "cliente": self.cliente,
                    "fecha_inicio": date(2026, 1, 1),
                    "fecha_vencimiento": date(2026, 4, 1),
                    "valor_prestamo": Decimal("100000.00"),
                },
                [{
                    "categoria": self.categoria,
                    "tipo_oro": self.tipo_oro,
                    "peso_gramos": Decimal("12.00"),
                }],
                self.usuario,
            )

    def test_crear_contrato_rechaza_prestamo_mayor_al_valor_calculado(self):
        with self.assertRaisesRegex(ValidationError, "valor calculado disponible"):
            crear_contrato(
                {
                    "cliente": self.cliente,
                    "fecha_inicio": date(2026, 1, 1),
                    "fecha_vencimiento": date(2026, 5, 1),
                    "valor_prestamo": Decimal("301000.00"),
                },
                [{
                    "categoria": self.categoria,
                    "tipo_oro": self.tipo_oro,
                    "peso_gramos": Decimal("1.00"),
                }],
                self.usuario,
            )

    def test_calcular_interes_por_periodo_fraccionario_confirmado(self):
        contrato = self.crear_contrato(date(2026, 1, 1), date(2026, 5, 1))

        interes = calcular_interes(contrato, date(2026, 4, 11))

        self.assertEqual(interes, Decimal("17500"))

    def test_calcular_interes_aumenta_tasa_por_mora_confirmada(self):
        contrato = self.crear_contrato(date(2026, 1, 1), date(2026, 5, 1))

        interes = calcular_interes(contrato, date(2026, 7, 1))

        self.assertEqual(interes, Decimal("36000"))

    def test_abono_cubre_interes_antes_de_reducir_capital(self):
        contrato = self.crear_contrato(date(2026, 1, 1), date(2026, 5, 1))
        fecha_pago = timezone.make_aware(datetime(2026, 2, 1, 12, 0))
        Pago.objects.create(
            contrato=contrato,
            empleado=self.usuario,
            fecha=fecha_pago,
            monto=Decimal("6000.00"),
            tipo=Pago.Tipo.ABONO,
        )

        self.assertEqual(calcular_saldo(contrato, date(2026, 3, 1)), Decimal("103950"))

    def test_renovacion_cobra_interes_y_extiende_vencimiento(self):
        hoy = timezone.localdate()
        contrato = self.crear_contrato(_sumar_meses(hoy, -4), hoy)

        pago = registrar_pago(
            contrato,
            calcular_interes(contrato, hoy),
            Pago.Tipo.RENOVACION,
            self.usuario,
        )

        contrato.refresh_from_db()
        self.assertEqual(pago.tipo, Pago.Tipo.RENOVACION)
        self.assertEqual(contrato.fecha_vencimiento, _sumar_meses(hoy, 4))
        self.assertEqual(
            calcular_interes(contrato, _sumar_meses(hoy, 1)), Decimal("5000")
        )

    def test_retiro_cierra_contrato_y_detiene_intereses(self):
        hoy = timezone.localdate()
        contrato = self.crear_contrato(hoy, _sumar_meses(hoy, 4))

        registrar_pago(
            contrato,
            Decimal("100000.00"),
            Pago.Tipo.RETIRO,
            self.usuario,
        )
        contrato.refresh_from_db()

        self.assertEqual(contrato.estado, Contrato.Estado.RETIRADO)
        self.assertEqual(calcular_saldo(contrato, _sumar_meses(hoy, 8)), Decimal("0"))

    def test_cliente_puede_retirar_contrato_vencido_durante_gracia(self):
        hoy = timezone.localdate()
        contrato = self.crear_contrato(
            _sumar_meses(hoy, -5),
            _sumar_meses(hoy, -1),
        )

        with patch("empenos.servicios.timezone.localdate", return_value=hoy):
            saldo = calcular_saldo(contrato, hoy)
            pago = registrar_pago(
                contrato,
                saldo,
                Pago.Tipo.RETIRO,
                self.usuario,
            )

        contrato.refresh_from_db()
        self.assertEqual(pago.tipo, Pago.Tipo.RETIRO)
        self.assertEqual(contrato.estado, Contrato.Estado.RETIRADO)

    def test_liquidar_contrato_vencido_despues_de_gracia_crea_prendas_trazables(self):
        vencimiento = date(2026, 1, 16)
        hoy = date(2026, 4, 16)
        contrato = self.crear_contrato(date(2025, 9, 16), vencimiento)
        articulos = [
            ArticuloEmpeno.objects.create(
                contrato=contrato,
                categoria=self.categoria,
                tipo_oro=self.tipo_oro,
                peso_gramos=Decimal(peso),
                valor_gramo_aplicado=self.tipo_oro.valor_prestamo_gramo,
            )
            for peso in ("1.00", "2.00")
        ]

        with patch("empenos.servicios.timezone.localdate", return_value=hoy):
            prendas = pasar_a_inventario(
                contrato,
                self.usuario,
                {articulos[0].pk: Decimal("150000"), articulos[1].pk: Decimal("250000")},
            )

        contrato.refresh_from_db()
        self.assertEqual(contrato.estado, Contrato.Estado.LIQUIDADO)
        self.assertEqual(len(prendas), 2)
        self.assertTrue(all(prenda.estado == Prenda.Estado.DISPONIBLE for prenda in prendas))
        self.assertTrue(
            all(prenda.origen == Prenda.Origen.EMPENO_VENCIDO for prenda in prendas)
        )
        self.assertEqual(
            [prenda.precio_venta for prenda in prendas],
            [Decimal("350000.00"), Decimal("700000.00")],
        )
        self.assertEqual(
            {prenda.articulo_origen_id for prenda in prendas},
            {articulo.pk for articulo in articulos},
        )

    def test_liquidar_antes_de_cumplir_gracia_es_rechazado(self):
        contrato = self.crear_contrato(date(2025, 9, 16), date(2026, 1, 16))
        articulo = ArticuloEmpeno.objects.create(
            contrato=contrato,
            categoria=self.categoria,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("1.00"),
            valor_gramo_aplicado=self.tipo_oro.valor_prestamo_gramo,
        )

        with patch(
            "empenos.servicios.timezone.localdate", return_value=date(2026, 4, 15)
        ):
            with self.assertRaises(ValidationError):
                pasar_a_inventario(
                    contrato, self.usuario, {articulo.pk: Decimal("150000")}
                )

        self.assertFalse(Prenda.objects.exists())

    def test_liquidar_exige_precio_positivo_para_cada_articulo(self):
        contrato = self.crear_contrato(date(2025, 9, 16), date(2026, 1, 16))
        tipo_oro = TipoOro.objects.create(
            nombre="Chino",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("200000.00"),
        )
        articulo = ArticuloEmpeno.objects.create(
            contrato=contrato,
            categoria=self.categoria,
            tipo_oro=tipo_oro,
            peso_gramos=Decimal("1.00"),
            valor_gramo_aplicado=tipo_oro.valor_prestamo_gramo,
        )

        with patch(
            "empenos.servicios.timezone.localdate", return_value=date(2026, 4, 16)
        ):
            with self.assertRaises(ValidationError):
                pasar_a_inventario(contrato, self.usuario, {})
            with self.assertRaises(ValidationError):
                pasar_a_inventario(
                    contrato, self.usuario, {articulo.pk: Decimal("0")}
                )

        self.assertFalse(Prenda.objects.exists())

    def test_anular_contrato_exige_observacion_y_conserva_registro(self):
        contrato = self.crear_contrato(date(2026, 1, 1), date(2026, 5, 1))

        with self.assertRaises(ValidationError):
            anular_contrato(contrato, self.usuario, "")
        anular_contrato(contrato, self.usuario, "Error de digitación")

        contrato.refresh_from_db()
        self.assertEqual(contrato.estado, Contrato.Estado.ANULADO)
        self.assertIn("Error de digitación", contrato.observaciones)
        self.assertTrue(Contrato.objects.filter(pk=contrato.pk).exists())
        self.assertEqual(calcular_saldo(contrato), Decimal("0"))
        with self.assertRaises(ValidationError):
            anular_contrato(contrato, self.usuario, "Segunda anulación")


class FormularioContratoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="empleado_web", password="clave")
        from django.contrib.auth.models import Group

        self.usuario.groups.add(Group.objects.create(name="Empleado"))
        self.cliente = Cliente.objects.create(
            documento="789", nombres="Cliente Web", telefono="3000000002"
        )
        self.tipo_oro = TipoOro.objects.create(
            nombre="Nacional Web",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("280000.00"),
        )
        self.categoria = Categoria.objects.create(nombre="Pulsera Web")
        RangoInteres.objects.create(
            monto_desde=Decimal("0.00"),
            monto_hasta=None,
            tasa_mensual=Decimal("5.00"),
        )
        self.client.force_login(self.usuario)

    def datos_contrato(self, total_formularios):
        datos = {
            "cliente": str(self.cliente.pk),
            "documento": "",
            "nombres": "",
            "telefono": "",
            "direccion": "",
            "fecha_inicio": "2000-01-01",
            "fecha_vencimiento": "2000-05-01",
            "valor_prestamo": "100000.00",
            "observaciones": "",
            "articulos-TOTAL_FORMS": str(total_formularios),
            "articulos-INITIAL_FORMS": "0",
            "articulos-MIN_NUM_FORMS": "1",
            "articulos-MAX_NUM_FORMS": "1000",
        }
        for indice in range(total_formularios):
            datos.update({
                f"articulos-{indice}-categoria": str(self.categoria.pk),
                f"articulos-{indice}-tipo_oro": str(self.tipo_oro.pk),
                f"articulos-{indice}-peso_gramos": "6.00",
                f"articulos-{indice}-descripcion": f"Pieza {indice + 1}",
            })
        return datos

    def test_formset_sin_articulos_es_invalido(self):
        datos = self.datos_contrato(1)
        for campo in (
            "articulos-0-categoria",
            "articulos-0-tipo_oro",
            "articulos-0-peso_gramos",
            "articulos-0-descripcion",
        ):
            datos.pop(campo)

        respuesta = self.client.post(reverse("empenos:contrato_crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Contrato.objects.exists())

    def test_formulario_guarda_dos_articulos_y_detalle(self):
        respuesta = self.client.post(
            reverse("empenos:contrato_crear"), self.datos_contrato(2)
        )

        contrato = Contrato.objects.get()
        self.assertRedirects(
            respuesta,
            reverse("empenos:contrato_detalle", args=[contrato.numero]),
        )
        self.assertEqual(contrato.articulos.count(), 2)
        self.assertEqual(
            contrato.valor_calculado_total, Decimal("3360000.000000")
        )
        self.assertEqual(
            list(contrato.articulos.values_list("valor_gramo_aplicado", flat=True)),
            [Decimal("280000.00"), Decimal("280000.00")],
        )
        hoy = timezone.localdate()
        self.assertEqual(contrato.fecha_inicio, hoy)
        self.assertEqual(
            contrato.fecha_vencimiento,
            _sumar_meses(hoy, 4),
        )
        detalle = self.client.get(
            reverse("empenos:contrato_detalle", args=[contrato.numero])
        )
        imprimible = self.client.get(
            reverse("empenos:contrato_imprimir", args=[contrato.numero])
        )
        self.assertContains(detalle, contrato.numero_formateado)
        self.assertContains(imprimible, contrato.numero_formateado)


class SimuladorPublicoTests(TestCase):
    def setUp(self):
        self.tipo_oro = TipoOro.objects.create(
            nombre="Tipo simulador",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("300000.00"),
        )
        self.categoria = Categoria.objects.create(nombre="Cadena simulador")
        RangoInteres.objects.create(
            monto_desde=Decimal("0.00"),
            monto_hasta=None,
            tasa_mensual=Decimal("5.00"),
        )

    def datos_simulador(self, prestamo="100000.00", peso="12.00"):
        return {
            "valor_prestamo": prestamo,
            "articulos-TOTAL_FORMS": "1",
            "articulos-INITIAL_FORMS": "0",
            "articulos-MIN_NUM_FORMS": "1",
            "articulos-MAX_NUM_FORMS": "5",
            "articulos-0-categoria": str(self.categoria.pk),
            "articulos-0-tipo_oro": str(self.tipo_oro.pk),
            "articulos-0-peso_gramos": peso,
        }

    def test_formulario_es_publico_y_inicia_con_un_articulo(self):
        respuesta = self.client.get(reverse("empenos:simulador"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["formset"].total_form_count(), 1)

    def test_visitante_simula_y_ve_proyeccion_sin_crear_registros(self):
        respuesta = self.client.post(
            reverse("empenos:simulador"),
            self.datos_simulador(),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Resumen del empeño simulado")
        self.assertContains(respuesta, "$ 27.500")
        self.assertContains(
            respuesta, "No aplica; no se ha creado un contrato oficial."
        )
        self.assertContains(respuesta, '"1": "300000.00"')
        self.assertEqual(
            respuesta.context["simulacion"]["fecha_vencimiento"],
            _sumar_meses(timezone.localdate(), 4),
        )
        self.assertEqual(Contrato.objects.count(), 0)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(ArticuloEmpeno.objects.count(), 0)

    def test_simulador_muestra_error_si_el_prestamo_supera_el_limite(self):
        respuesta = self.client.post(
            reverse("empenos:simulador"),
            self.datos_simulador(prestamo="4000000.00"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "valor calculado disponible")
        self.assertIsNone(respuesta.context["simulacion"])
        self.assertEqual(Contrato.objects.count(), 0)


class AccionesContratoViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_contratos")
        self.admin.groups.add(Group.objects.create(name="Administrador"))
        self.empleado = User.objects.create_user(username="empleado_contratos")
        self.empleado.groups.add(Group.objects.create(name="Empleado"))
        cliente = Cliente.objects.create(
            documento="987", nombres="Cliente Acciones", telefono="3000000003"
        )
        self.tipo_oro = TipoOro.objects.create(
            nombre="Chino Acciones",
            valor_gramo=Decimal("100000.00"),
            valor_prestamo_gramo=Decimal("200000.00"),
        )
        categoria = Categoria.objects.create(nombre="Aro Acciones")
        self.contrato = Contrato.objects.create(
            numero=801,
            cliente=cliente,
            empleado=self.empleado,
            fecha_inicio=_sumar_meses(timezone.localdate(), -7),
            fecha_vencimiento=_sumar_meses(timezone.localdate(), -3),
            valor_prestamo=Decimal("100000.00"),
            tasa_aplicada=Decimal("5.00"),
        )
        self.articulo = ArticuloEmpeno.objects.create(
            contrato=self.contrato,
            categoria=categoria,
            tipo_oro=self.tipo_oro,
            peso_gramos=Decimal("10.00"),
            valor_gramo_aplicado=self.tipo_oro.valor_prestamo_gramo,
        )

    def test_empleado_registra_abono_desde_la_vista(self):
        self.client.force_login(self.empleado)

        respuesta = self.client.post(
            reverse("empenos:contrato_pago", args=[self.contrato.numero]),
            {
                "tipo": Pago.Tipo.ABONO,
                "monto": "1000.00",
                "observaciones": "Pago parcial",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("empenos:contrato_detalle", args=[self.contrato.numero]),
        )
        pago = Pago.objects.get(contrato=self.contrato)
        self.assertEqual(pago.monto, Decimal("1000.00"))
        self.assertEqual(pago.observaciones, "Pago parcial")

    def test_administrador_liquida_y_guarda_precio_inicial(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("empenos:contrato_liquidar", args=[self.contrato.numero]),
            {
                "precios-TOTAL_FORMS": "1",
                "precios-INITIAL_FORMS": "0",
                "precios-MIN_NUM_FORMS": "0",
                "precios-MAX_NUM_FORMS": "1000",
                "precios-0-articulo_id": str(self.articulo.pk),
                "precios-0-precio_venta": "250000.00",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("empenos:contrato_detalle", args=[self.contrato.numero]),
        )
        self.contrato.refresh_from_db()
        prenda = Prenda.objects.get()
        self.assertEqual(self.contrato.estado, Contrato.Estado.LIQUIDADO)
        self.assertEqual(prenda.precio_venta, Decimal("250000.00"))
        self.assertEqual(prenda.articulo_origen, self.articulo)

    def test_empleado_no_puede_liquidar_por_la_vista(self):
        self.client.force_login(self.empleado)

        respuesta = self.client.get(
            reverse("empenos:contrato_liquidar", args=[self.contrato.numero])
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_anula_y_registra_observacion(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("empenos:contrato_anular", args=[self.contrato.numero]),
            {"observacion": "Solicitud del cliente"},
        )

        self.assertRedirects(
            respuesta,
            reverse("empenos:contrato_detalle", args=[self.contrato.numero]),
        )
        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.estado, Contrato.Estado.ANULADO)
        self.assertIn("Solicitud del cliente", self.contrato.observaciones)
