from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView

from core.permisos import EmpleadoRequeridoMixin

from . import servicios
from .forms import DetalleVentaFormSet, VentaForm
from .models import Venta


class PanelEmpleadoMixin(LoginRequiredMixin, EmpleadoRequeridoMixin):
    pass


class VentaListaView(PanelEmpleadoMixin, ListView):
    model = Venta
    template_name = "ventas/venta_list.html"
    context_object_name = "ventas"
    paginate_by = 10

    def get_queryset(self):
        return Venta.objects.select_related(
            "cliente", "empleado"
        ).prefetch_related("detalles__prenda__categoria")


class VentaCrearView(PanelEmpleadoMixin, FormView):
    template_name = "ventas/venta_form.html"
    form_class = VentaForm

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.setdefault(
            "formset", DetalleVentaFormSet(prefix="detalles")
        )
        return contexto

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        formset = DetalleVentaFormSet(
            request.POST, prefix="detalles"
        )
        if form.is_valid() and formset.is_valid():
            articulos = [
                {
                    "prenda_id": fila["prenda"].pk,
                    "precio_final": fila["precio_final"],
                }
                for fila in formset.cleaned_data
            ]
            try:
                venta = servicios.registrar_venta(
                    request.user,
                    articulos,
                    cliente=form.cleaned_data["cliente"],
                )
            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            else:
                messages.success(request, "Venta registrada correctamente.")
                return redirect("ventas:lista")
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def get_success_url(self):
        return reverse_lazy("ventas:lista")
