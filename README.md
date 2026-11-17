# Joyería y Compraventa

Aplicación web académica para administrar clientes, contratos de empeño,
inventario y ventas de una joyería. Está desarrollada con Django y utiliza
plantillas renderizadas en el servidor.

## Tecnologías

- Python 3.12 o superior
- Django 5.2
- SQLite para desarrollo
- Pillow para el manejo de imágenes
- Bootstrap 5.3

## Funcionalidades

- Gestión de clientes, empleados y administradores.
- Creación y consulta de contratos de empeño con sus prendas.
- Fechas de inicio y vencimiento automáticas: el plazo inicial es de cuatro
  meses calendario.
- Registro de abonos, renovaciones, retiros y liquidaciones.
- Consulta de intereses, saldos y vencimientos.
- Inventario de prendas disponibles y registro de ventas.
- Catálogo público de prendas Italianas y Nacionales.
- Simulador público de empeño que muestra el valor prestable y una proyección
  de intereses sin crear un contrato.
- Consulta de la cotización internacional del oro y actualización de las
  tarifas de compra.
- Portal para clientes, con acceso limitado a sus propios contratos. Los
  clientes registrados por un empleado pueden crear sus credenciales desde la
  pantalla de inicio de sesión.

## Reglas principales

### Empeños e intereses

- El valor máximo prestable se calcula por gramo: Italiano $300.000, Nacional
  $280.000, 14k $250.000 y Chino $200.000.
- El valor calculado de las prendas se redondea una vez hacia abajo al millar.
  El préstamo mínimo es de $50.000 y se puede solicitar un monto menor al
  máximo calculado.
- La tasa mensual se selecciona según el rango de monto configurado y se
  aplica al capital pendiente.
- Los intereses se calculan hasta la fecha de cada pago. Para fracciones de
  mes, de 1 a 15 días se cuenta medio mes y de 16 días en adelante, un mes.
- Durante la mora, la tasa aumenta 0,5 puntos porcentuales por cada mes de
  retraso. Un abono cubre primero los intereses acumulados y luego reduce el
  capital.
- Para renovar, el cliente paga los intereses acumulados hasta la fecha. La
  nueva fecha de vencimiento se calcula cuatro meses calendario después del
  vencimiento anterior.
- Después del vencimiento hay tres meses calendario de gracia. Durante ese
  periodo se permite renovar o retirar las prendas.
- Las tasas y los rangos de interés se configuran en la aplicación. Los datos
  de demostración no representan condiciones comerciales vigentes.

### Catálogo y ventas

- Solo se publican y venden prendas de oro Italiano y Nacional.
- La tarifa de venta es $350.000 por gramo para Italiano y $330.000 por gramo
  para Nacional.
- El precio sugerido se calcula a partir del peso y la tarifa de venta. Al
  registrar una venta, el empleado puede establecer el precio final.

### Compra de oro

- La cotización XAU/COP de GoldAPI.io se combina con la pureza configurada para
  cada tipo de oro.
- La tarifa de compra publicada corresponde al 95% del valor referencial.
- Estas tarifas son independientes de los valores usados para calcular
  préstamos de empeño y precios de venta del catálogo.

## Instalación y ejecución

Desde PowerShell, en la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py crear_roles
python manage.py cargar_datos_demo
python manage.py runserver
```

La aplicación estará disponible en <http://127.0.0.1:8000/>.

El comando `cargar_datos_demo` crea clientes, contratos, prendas y cuentas de
prueba. Solo se puede ejecutar con `DEBUG` activado. Las cuentas DEMO comparten
una contraseña de prueba que el comando informa al crearlas. Para restablecer
las contraseñas y volver a mostrarlas:

```powershell
python manage.py cargar_datos_demo --reset-demo-passwords
```

Usa las cuentas y los datos DEMO únicamente en desarrollo.

## Cotización del oro

Para consultar la API se necesita un token de GoldAPI.io. Configúralo en la
variable de entorno `GOLDAPI_TOKEN` y ejecuta el comando de actualización:

```powershell
$env:GOLDAPI_TOKEN = "tu-token"
python manage.py actualizar_precios_oro
```

El comando guarda la cotización y actualiza las tarifas de compra. Para
mantenerlas vigentes, vuelve a ejecutarlo periódicamente de acuerdo con los
límites de consulta de tu plan de API. Si la consulta falla, se conservan los
últimos valores disponibles.

## Configuración para otros entornos

En desarrollo, `DEBUG` está activado de forma predeterminada. Antes de ejecutar
la aplicación en un entorno distinto, configura `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG=False` y `DJANGO_ALLOWED_HOSTS`. No publiques claves ni tokens.

La aplicación no incluye una base de datos con información local en el
repositorio. Las migraciones crean la estructura y el comando DEMO carga datos
ficticios.

## Pruebas y verificaciones

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```
