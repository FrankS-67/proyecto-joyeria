from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission


class Command(BaseCommand):
    help = "Crea de forma idempotente los grupos Empleado, Administrador y Cliente."

    def handle(self, *args, **options):
        for nombre in ("Empleado", "Administrador", "Cliente"):
            grupo, creado = Group.objects.get_or_create(name=nombre)
            if nombre == "Administrador":
                grupo.permissions.set(Permission.objects.all())
            accion = "creado" if creado else "ya existía"
            self.stdout.write(f"Grupo {nombre}: {accion}.")
