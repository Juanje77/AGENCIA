# Sistema para agencia de viajes

Dos herramientas sobre un mismo motor fiscal:

1. **Cotizador** — arma la propuesta al pasajero con varias opciones de mayoristas
   y muestra cuánto queda de ganancia después de impuestos.
2. **Liquidador** — lee las facturas que mandan los mayoristas (PDF, incluso
   escaneadas) y arma la posición de **IVA e Ingresos Brutos** del período.

Corre en la computadora de la agencia. No manda datos a ningún lado.

---

## Puesta en marcha

Hay dos maneras de usarlo y el sistema funciona igual en las dos.

### Publicado en Vercel

1. Entrá a [vercel.com](https://vercel.com), creá una cuenta e importá este
   repositorio ("Add New… → Project").
2. Vercel detecta la configuración solo. Dale **Deploy** y esperá un minuto.
3. Te queda una dirección para entrar desde cualquier lado, también del celular.

**Ponele una clave antes de cargar facturas reales.** En Vercel, en
*Settings → Environment Variables*, agregá:

| Nombre | Valor |
|---|---|
| `AGENCIA_CLAVE` | la contraseña que quieras |

Sin esa variable, cualquiera con el link entra. Después de agregarla hay que
volver a hacer *Deploy* para que tome efecto. La primera vez que entres te la
va a pedir.

En Vercel el disco no se puede escribir, así que **la configuración de
mayoristas la guarda tu navegador**. Eso tiene una ventaja: los datos de la
agencia quedan en tu computadora, no en el servidor. Y una consecuencia: si
entrás desde otra computadora o borrás los datos del navegador, hay que
cargarlos de nuevo.

En Vercel no se puede instalar el reconocimiento de texto propio (Tesseract es
un programa del sistema operativo), así que **las facturas escaneadas se leen
con IA**. Para habilitarla, agregá también:

| Nombre | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | tu clave de [console.anthropic.com](https://console.anthropic.com) |

Sin esa clave el sistema funciona igual, pero las facturas escaneadas hay que
cargarlas a mano.

### En una computadora

```bash
pip install -r requirements.txt
python iniciar.py
```

En Windows y Mac alcanza con hacer doble clic en `iniciar.bat` o
`iniciar.command`: instalan lo que falte, levantan el sistema y abren el
navegador solos.

Así sí funcionan las facturas escaneadas, instalando además el OCR
(ver más abajo).

---

## Primeros pasos

La primera vez, entrá a **Mayoristas** y cargá:

- el **CUIT de la agencia** — sirve para que el sistema reconozca, en cada
  factura, si la agencia es quien emite o quien recibe;
- el **porcentaje de comisión** que te reconoce cada mayorista y el IVA que
  aplica sobre ella;
- los nombres con los que cada mayorista aparece en sus facturas, para que
  las reconozca solas.

---

## Cotizador

Cada cotización tiene varias **opciones** y cada opción se carga de dos maneras:

- **desglosada**: servicio por servicio (aéreo, hotel, traslado, asistencia),
  cada uno con su tarifa, su comisión y sus gastos administrativos;
- **paquete cerrado**: el mayorista pasa un precio único con una parte comisionable.

Las reglas de cálculo son las que usa la agencia:

| Concepto | Cómo se calcula | ¿Se le suma al pasajero? | ¿Es ganancia? |
|---|---|---|---|
| Comisión | % sobre la tarifa | No, ya viene adentro | Sí |
| Gastos administrativos | % sobre (tarifa − comisión) | Sí | No |
| Impuestos | % sobre (comisión + gastos) | Sí | No, los descuenta |
| Precio forzado por pax | lo que definas | Sí | Sí, la diferencia |

Salidas: **propuesta para el cliente** (solo precios) y **análisis para la
agencia** (comisiones, impuestos y ganancia por opción), ambas imprimibles.

### El contraste fiscal

El presupuesto carga un porcentaje de impuestos plano. El sistema además calcula
la carga **real** según el tratamiento que le corresponde a cada tipo de
servicio, y muestra la diferencia. Por ejemplo: la comisión de un aéreo
internacional no lleva IVA, así que cargar 21% sobre ella encarece el
presupuesto sin necesidad.

---

## Liquidador

Arrastrás las facturas de los mayoristas y el sistema arma una fila por cada una.

Lo que lee de cada factura:

- tipo, punto de venta y número, fecha, CAE;
- CUIT del emisor y del receptor, para saber el sentido de la operación;
- neto gravado por alícuota, IVA 21% y 10,5%, exento, no gravado, percepciones
  y total;
- moneda y tipo de cambio;
- file o legajo y nombre de los pasajeros.

Después reparte esos importes en las dos columnas que necesita la liquidación:

- **comisionable**: el servicio en sí (gravado + exento), que es sobre lo que el
  mayorista reconoce la comisión;
- **no comisionable**: tasas, cargos e impuestos que no pagan comisión.

### Cómo se determinan los impuestos

```
comisión ganada   = comisionable × % del mayorista      (viene con IVA adentro)
gravado           = comisión ganada ÷ 1,21              (comisión neta)
IVA de comisión   = comisión ganada − gravado

servicio propio   = total del viaje × % de servicio     (neto)
IVA de servicio   = servicio propio × 21%

DÉBITO FISCAL     = IVA de comisión + IVA de servicio
BASE DE IIBB      = gravado + servicio propio
IIBB              = base × alícuota de la jurisdicción
```

Todo se expresa en pesos. Las facturas en dólares se convierten al tipo de
cambio que informa el propio comprobante.

### El crédito fiscal, que conviene definir con el contador

Cuando el mayorista factura con IVA discriminado (factura A), ese IVA aparece
como crédito fiscal **posible**, pero viene desactivado. La razón:

- si la agencia actúa **como intermediaria** por cuenta y orden de terceros,
  factura solo su comisión y ese IVA no es suyo: el destinatario del servicio es
  el pasajero;
- si **revende por cuenta propia** y le factura al pasajero el viaje completo,
  entonces sí lo computa.

El sistema avisa cuánto IVA está dejando afuera para que la decisión sea explícita.

---

## Lectura de facturas

Cada mayorista arma la factura a su manera. El lector reconoce tres formas de
pie de totales:

- **vertical** — una etiqueta y su importe por renglón
  (`Importe Neto Gravado AR$ 1.080.749,58`);
- **horizontal** — un renglón de etiquetas y el siguiente con los importes
  alineados por columna (`Exento | No Gravado | Gravado 21% | ...`);
- **en pares** — dos por renglón (`Gravado 21%: 84,11   Iva 21%: 17,66`).

Después **controla que los importes cierren contra el total**. Si no cierran, o
si algún dato se dedujo en vez de leerse, la factura queda marcada y lo dice.
Ese control es lo que permite confiar en lo que se leyó.

### Las que el lector no entiende

Hay tres caminos, y el sistema los prueba en orden:

1. **El lector de reglas.** No cuesta nada y responde en centésimas de segundo.
   Es el que se usa siempre que alcance.
2. **OCR** (`pytesseract` + Tesseract), para escaneos, si está instalado.
3. **IA**, si hay una `ANTHROPIC_API_KEY` cargada.

La IA **solo entra cuando los dos anteriores no llegaron**: un formato
desconocido, un escaneo sin OCR, o importes que no cierran contra el total. Si
el lector de reglas acierta —como pasa con la mayoría de las facturas— no se
gasta nada.

Lo que devuelve el modelo **pasa por el mismo control aritmético** que el
lector de reglas: si los importes no suman el total, la factura queda marcada
igual. Un modelo puede equivocarse en un dígito, y eso en una liquidación no
puede pasar inadvertido. Además, toda factura leída con IA queda señalada para
que revises los importes, y si el modelo avisa que algo estaba borroso, también
se registra.

Podés desactivarla desde la pantalla de liquidación, o por código:

```python
leer_factura(ruta, usar_ia="nunca")    # solo reglas, sin costo ni envío a terceros
leer_factura(ruta, usar_ia="auto")     # reglas primero, IA si hace falta (por defecto)
leer_factura(ruta, usar_ia="siempre")  # directo a la IA
```

**Qué cuesta.** Con `claude-opus-5`, leer una factura ronda los USD 0,03
(estimado sobre ~3.000 tokens de entrada y ~600 de salida, a USD 5 y USD 25 por
millón). Si de cada diez facturas hay que mandar dos al modelo, son unos USD
0,06 por mes cada diez facturas. Se puede abaratar con un modelo más chico:

```
AGENCIA_MODELO_IA=claude-haiku-4-5
```

**Qué se manda.** La factura entera, con los nombres de los pasajeros y los
CUIT. Si eso no te sirve, usá `usar_ia="nunca"` o el OCR local.

### Motores de PDF

Se prueban en orden y se usa el primero disponible: `pymupdf`, `pdfplumber`,
`pdfminer.six`, `PyPDF2`. Si un motor falla, sigue con el siguiente.

---

## Variables de entorno

| Variable | Para qué |
|---|---|
| `AGENCIA_CLAVE` | Clave de acceso. Si está vacía, el sistema queda abierto. |
| `AGENCIA_PUERTO` | Puerto del servidor local (8000 por defecto). |
| `AGENCIA_SOLO_LECTURA` | Fuerza el modo sin disco. Se detecta solo en Vercel. |
| `AGENCIA_CONFIG_DIR` | Otra carpeta de configuración. |
| `ANTHROPIC_API_KEY` | Habilita la lectura con IA. Sin ella, solo el lector de reglas. |
| `AGENCIA_MODELO_IA` | Qué modelo usar (`claude-opus-5` por defecto). |

---

## Línea de comandos

```bash
agencia factura facturas/*.pdf --periodo 09/2026 --html informe.html
agencia cotizacion ejemplos/cotizacion_bariloche.json --cliente propuesta.html
agencia mayoristas          # los mayoristas configurados
agencia parametros          # el tratamiento fiscal de cada servicio
agencia servidor            # la interfaz web
```

`agencia factura` devuelve código 3 si alguna factura no se pudo leer, para
poder encadenarlo en un script.

### Planillas en vez de facturas

Si un mayorista manda una planilla con el detalle de reservas en lugar de una
factura, hay un segundo camino que detecta las columnas solo:

```bash
agencia liquidacion planilla.csv --mayorista Ola --periodo 2026-09
agencia posicion liquidaciones/*.csv --periodo 2026-09
```

Reconoce los encabezados por sinónimos (`File`, `Nro Reserva`, `Comisión`,
`IVA s/Comisión`…), informa qué columna interpretó como qué, recalcula los
impuestos y marca las diferencias contra lo liquidado.

---

## Configuración

| Archivo | Qué guarda |
|---|---|
| `config/mayoristas.json` | Datos de la agencia y de cada mayorista |
| `config/parametros_fiscales.json` | Alícuotas, tratamiento por servicio, retenciones |
| `config/mayoristas/*.json` | Perfiles de columnas para planillas |

### Los parámetros fiscales hay que validarlos

`config/parametros_fiscales.json` define el tratamiento de IVA de cada tipo de
servicio (aéreo internacional exento, cabotaje al 10,5%, hotelería en el
exterior fuera del objeto, etc.) y las alícuotas de Ingresos Brutos por
jurisdicción.

**Los valores que vienen cargados son un punto de partida, no una verdad.** Las
alícuotas de Ingresos Brutos y los regímenes de retención están marcados con
`"verificar": true` y el sistema lo repite en cada informe hasta que los
confirmes con tu contador y saques la marca.

---

## Desarrollo

```bash
python -m pytest              # 242 tests
python herramientas/generar_factura_ejemplo.py ejemplos/
```

Estructura:

```
api/index.py              punto de entrada de Vercel (WSGI)
iniciar.py                arranque local, sin instalar nada
src/agencia/
  liquidador.py           liquidación del período (IVA e IIBB)
  liquidaciones/
    factura.py            lectura de facturas argentinas
    lectura_ia.py         respaldo con un modelo de visión
    lectores/pdf_texto.py extracción de texto multi-motor y OCR
    conciliacion.py       control de planillas contra el recálculo
  presupuestos/
    cotizacion.py         cotizador por opciones
  impuestos/              motor fiscal: IVA, IIBB, retenciones
  web/
    rutas.py              las rutas, compartidas por los dos entornos
    servidor.py           servidor local (http.server)
    informes.py           salidas imprimibles
  cli.py
```

Los importes se manejan con `Decimal` de punta a punta: un centavo de diferencia
por redondeo de punto flotante aparecería como una diferencia de conciliación
falsa.

---

## Privacidad

Las facturas traen nombres de pasajeros, CUIT y números de documento.

- El `.gitignore` excluye `facturas/`, `liquidaciones/` y `salidas/` para que no
  terminen en el repositorio. Los archivos de `ejemplos/` son generados, no reales.
- El sistema **no guarda las facturas**: las lee, extrae los importes y borra el
  archivo temporal. Nada queda en el servidor.
- La lectura con IA **sí manda la factura** a la API de Anthropic para que la
  interprete. Se usa solo cuando el lector de reglas no llega, y se puede
  desactivar desde la pantalla de liquidación.
- Los datos de la agencia y de los mayoristas se guardan en tu navegador cuando
  corre en Vercel, y en `config/mayoristas.json` cuando corre en tu computadora.
- Si lo publicás en internet, **poné `AGENCIA_CLAVE`**. Sin eso, cualquiera con
  el link puede subir y ver facturas.

---

Los importes que calcula el sistema son una herramienta de gestión.
Validalos con tu contador antes de presentar declaraciones juradas.
