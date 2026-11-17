from django.contrib.auth.mixins import UserPassesTestMixin


class EmpleadoRequeridoMixin(UserPassesTestMixin):
    def test_func(self):
        usuario = self.request.user
        return usuario.is_superuser or usuario.groups.filter(
            name__in=["Empleado", "Administrador"]
        ).exists()


class AdministradorRequeridoMixin(UserPassesTestMixin):
    def test_func(self):
        usuario = self.request.user
        return usuario.is_superuser or usuario.groups.filter(
            name="Administrador"
        ).exists()


class ClienteRequeridoMixin(UserPassesTestMixin):
    def test_func(self):
        usuario = self.request.user
        return (
            usuario.is_authenticated
            and usuario.groups.filter(name="Cliente").exists()
            and hasattr(usuario, "perfil_cliente")
        )
