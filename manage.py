#!/usr/bin/env python
"""Utilidad de linea de comandos para administrar el proyecto."""
import os
import sys


def main():
    """Ejecuta comandos administrativos."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Comprueba que esté instalado y "
            "disponible en PYTHONPATH, y que el entorno virtual esté activo."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
