from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView, TemplateView

from core.permisos import AdministradorRequeridoMixin, ClienteRequeridoMixin
from empenos import servicios as servicios_empeno
from empenos.models import Contrato
from inventario.models import Categoria, CotizacionOro, TipoOro
from ventas.models import Venta

from .forms import RegistroClienteForm, ReporteForm


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["categorias"] = Categoria.objects.order_by("nombre")
        contexto["tipos_oro"] = TipoOro.objects.order_by("nombre")
        contexto["cotizacion_oro"] = CotizacionOro.objects.first()
        return contexto


class RegistroClienteView(FormView):
    template_name = "registration/registro_cliente.html"
    form_class = RegistroClienteForm

    def form_valid(self, form):
        try:
            form.save()
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error(
                None,
                "No fue posible crear la cuenta. Verifica los datos o solicita ayuda en la tienda.",
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Cuenta creada. Ingresa con tu documento como usuario y la contraseña elegida.",
        )
        return redirect("login")


class MiCuentaView(LoginRequiredMixin, ClienteRequeridoMixin, TemplateView):
    template_name = "core/mi_cuenta.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        cliente = self.request.user.perfil_cliente
        contratos = list(
            Contrato.objects.filter(cliente=cliente)
            .prefetch_related("articulos__categoria", "articulos__tipo_oro")
            .order_by("-fecha_inicio", "-numero")
        )
        for contrato in contratos:
            contrato.interes_actual = servicios_empeno.calcular_interes(contrato)
            contrato.saldo_actual = servicios_empeno.calcular_saldo(contrato)
        contexto.update(cliente=cliente, contratos=contratos)
        return contexto


class ReporteView(LoginRequiredMixin, AdministradorRequeridoMixin, FormView):
    template_name = "core/reportes.html"
    form_class = ReporteForm

    def get_initial(self):
        hoy = timezone.localdate()
        return {
            "desde": hoy.replace(day=1),
            "hasta": hoy,
        }

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        form = contexto["form"]
        if form.is_bound:
            valido = form.is_valid()
            if valido:
                desde = form.cleaned_data["desde"]
                hasta = form.cleaned_data["hasta"]
            else:
                desde = self.get_initial()["desde"]
                hasta = self.get_initial()["hasta"]
        else:
            desde = self.get_initial()["desde"]
            hasta = self.get_initial()["hasta"]

        hoy = timezone.localdate()
        contratos_activos = Contrato.objects.filter(
            estado=Contrato.Estado.ACTIVO,
            fecha_vencimiento__gte=hoy,
        ).select_related("cliente").order_by("fecha_vencimiento")
        contratos_vencidos = Contrato.objects.filter(
            estado=Contrato.Estado.ACTIVO,
            fecha_vencimiento__lt=hoy,
        ).select_related("cliente").order_by("fecha_vencimiento")
        ventas_periodo = Venta.objects.filter(
            fecha__date__gte=desde,
            fecha__date__lte=hasta,
        ).select_related("cliente").order_by("-fecha")
        contexto.update(
            contratos_activos=contratos_activos,
            contratos_vencidos=contratos_vencidos,
            total_contratos_activos=contratos_activos.count(),
            total_contratos_vencidos=contratos_vencidos.count(),
            ventas_periodo=ventas_periodo,
            total_ventas=ventas_periodo.aggregate(total=Sum("total"))["total"] or 0,
            cantidad_ventas=ventas_periodo.count(),
            desde=desde,
            hasta=hasta,
        )
        return contexto

    def form_valid(self, form):
        return self.render_to_response(
            self.get_context_data(form=form)
        )

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form), status=400)


def pagina_no_encontrada(request, exception):
    from django.shortcuts import render

    return render(request, "404.html", status=404)


def permiso_denegado(request, exception):
    from django.shortcuts import render

    return render(request, "403.html", status=403)
