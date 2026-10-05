# Sistema para agencia de viajes

Dos partes con público distinto:

- **`/` — sitio público** (marca Esplora): lo que ve un cliente potencial. No
  pide clave, no toca el motor fiscal.
- **`/panel` — herramientas internas**, sobre un mismo motor fiscal:
  1. **Cotizador** — arma la propuesta al pasajero con varias opciones de
     mayoristas y muestra cuánto queda de ganancia después de impuestos.
  2. **Liquidador** — lee las facturas que mandan los mayoristas (PDF, incluso
     escaneadas) y arma la posición de **IVA e Ingresos Brutos** del período.

El panel queda protegido por `AGENCIA_CLAVE` (ver [Variables de
entorno](#variables-de-entorno)); el sitio público nunca la pide.

---

## Sitio público (`/`)

Landing con la identidad de marca **Esplora — Viajes y Turismo**: paleta
terracota/buttercream, Playfair Display + Montserrat + Allura, con el logo
real de la marca. No depende del resto del sistema, son páginas estáticas.

Está repartido en varias páginas en vez de una sola muy larga:

| Página | Contenido |
|---|---|
| `/` | Inicio: hero + un resumen breve de cada sección de abajo, con su link a la página completa |
| `/servicios` | Grilla con los productos que se venden (espejo de la franja del header) + "Consejos para elegir tu viaje" |
| `/servicios/aereos`, `/…/hoteles`, `/…/circuitos`, `/…/assist-card`, `/…/cruceros`, `/…/actividades`, `/…/autos`, `/…/traslados`, `/…/disney`, `/…/universal`, `/…/enjoy` | Una página propia por cada producto — misma lista y mismo orden que el menú de servicios de **ola.com.ar** (el mayorista con el que se trabaja), para que cada ítem de la franja del header lleve a su propia página en vez de todo apilado en `/servicios` |
| `/destinos` | Las 4 categorías de "Para inspirarte" |
| `/salidas-grupales` | Las salidas con fecha fija, cupo y precio cerrado — nacionales e internacionales juntas —, con su botón de Mercado Pago |
| `/salidas-grupales/bariloche`, `/…/iguazu`, `/…/mendoza`, `/…/calafate`, `/…/punta-cana`, `/…/vina-del-mar` | Itinerario día por día de cada salida grupal, con horarios, incluye/no incluye y el botón de pago |
| `/a-medida` | Los destinos de referencia sin fecha fija: el precio final se cotiza caso por caso |
| `/nosotros` | Cómo trabajamos, paso a paso, y el testimonio |
| `/contacto` | Datos de contacto y el formulario |
| `/panel` | Herramientas internas (protegidas por `AGENCIA_CLAVE`) |
| `/robots.txt`, `/sitemap.xml` | Para buscadores — se generan solos a partir de `PAGINAS_PUBLICAS` en `rutas.py`, no hay archivos estáticos que tocar |

Cada página es un archivo en `src/agencia/web/estatico/` (`publico.html`,
`servicios.html`, `servicio-aereos.html`, `servicio-hoteles.html`,
`servicio-circuitos.html`, `servicio-assist-card.html`, `servicio-cruceros.html`,
`servicio-actividades.html`, `servicio-autos.html`, `servicio-traslados.html`,
`servicio-disney.html`, `servicio-universal.html`, `servicio-enjoy.html`,
`destinos.html`, `salidas-grupales.html`, `a-medida.html`, `nosotros.html`,
`contacto.html`). El header, el pie de página y los íconos
SVG **no están duplicados** en cada uno: viven una sola vez en
`src/agencia/web/estatico/_partes/` (`encabezado.html`, `pie.html`,
`iconos.html`) y el servidor los inserta al vuelo donde cada página tiene el
comentario `<!--ENCABEZADO-->`, `<!--PIE-->` o `<!--ICONOS-->` (función
`_pagina_publica()` en `rutas.py`). Para cambiar un link del menú o algo del
pie de página alcanza con editar ese archivo una sola vez.

Todas las páginas comparten `publico.css`/`publico.js`. Las páginas que no
son el inicio llevan `<body class="pagina-interna">`: como no tienen la foto
del hero detrás, el header no puede empezar transparente como en `/` — esa
clase le pone el mismo fondo sólido que el header adopta al hacer scroll en
el inicio.

El logo (isotipo círculo + avión) se procesó a partir de los archivos que
pasó la agencia para sacarle el fondo, y quedó en dos versiones en
`src/agencia/web/estatico/img/`: `logo-icono-oscuro.png` (tinta oscura, para
fondos claros) y `logo-icono-claro.png` (tinta clara, para fondos oscuros o
sobre la foto del hero). Se usa así en el header (cambia solo al hacer
scroll), en el pie de página, en el panel interno y como favicon. El
lockup completo con el nombre y "VIAJES Y TURISMO" (`logo-horizontal-*.png`)
también quedó guardado ahí por si sirve para papelería o redes, pero no se
usa en la página: a los tamaños de un header el subtítulo se ve borroso, así
que el nombre se sigue mostrando como texto (nítido a cualquier tamaño) al
lado del ícono. La foto-flyer que mandó la agencia (`hero-esplora.jpg`) se
usa como imagen de vista previa al compartir el link (`og:image`).

El fondo del hero (la sección de arriba de todo en `/`) es una foto real
de playa (`hero-playa.jpg`, 1717×916) que mandó la agencia. Al ser una
sección a pantalla completa, conviene que cualquier reemplazo futuro tenga
un ancho similar o mayor — con una foto más chica se nota borrosa al
estirarse en monitores grandes.

**Antes de publicarlo a clientes reales, completá lo que quedó de referencia:**

| Dónde | Qué reemplazar |
|---|---|
| `contacto.html` y `_partes/pie.html` | Email y dirección — están marcados con `<!-- COMPLETAR -->` (el teléfono y el WhatsApp ya son los reales: +54 9 2954 44-7929) |
| `contacto.html` | Enlaces de Instagram y Facebook (hoy apuntan a `#`; el de WhatsApp ya está) |
| `contacto.py` | El email de destino del formulario (`hola@esplora.com.ar` es de ejemplo; se puede cambiar sin tocar código con `CONTACTO_EMAIL`, ver [Variables de entorno](#variables-de-entorno)) |
| `salidas-grupales.html` | 6 salidas de ejemplo: las 4 nacionales (Bariloche, Iguazú, Mendoza, El Calafate) y 2 internacionales (Punta Cana vía el mayorista Ola, y Viña del Mar como salida propia en micro) — buscá el comentario `<!-- COMPLETAR -->` arriba de `<div class="grilla-flyers">` |
| `a-medida.html` | 4 destinos de ejemplo (Cancún, Río de Janeiro, París/Roma, Orlando) con precio de referencia — buscá el comentario arriba de `<div class="grilla-flyers">` |
| `DOMINIO_PUBLICO` en `rutas.py` | Hoy dice `https://www.esplora.com.ar` de referencia — reemplazalo por el dominio real (propio, o el `*.vercel.app` del despliegue) una vez que lo tengas. Lo usan `/sitemap.xml`, `/robots.txt` y los tags Open Graph/Twitter Card de cada página (las imágenes que se comparten al pegar un link en WhatsApp o redes) |

**El formulario de contacto** (`/contacto`) manda la consulta al endpoint
`/api/contacto`, que la envía por correo a la agencia usando SMTP
(`SMTP_HOST` y las variables relacionadas, ver abajo). Mientras esas
variables no estén cargadas en el hosting, el formulario sigue funcionando
igual que antes: se abre el programa de correo del cliente con la consulta
ya redactada.

**Los botones de "pedir cotización" o "contacto"** repartidos por todo el
sitio (el del header, los de cada tarjeta de "A medida", los
"Escribinos" de cada página, etc.) no pasan por ese formulario: abren
directo una conversación de WhatsApp al +54 9 2954 44-7929, con el mensaje
ya redactado según de dónde salió el click. La única puerta que sigue
llevando al formulario es el link "Contacto" de la navegación (header y
pie de página), para quien prefiera escribir en vez de usar WhatsApp. Si
cambia el número, el texto a reemplazar es `5492954447929` — aparece en
`_partes/encabezado.html`, `_partes/pie.html` y en cada página pública que
tenga uno de estos botones.

**Sobre las fotos:** las 4 tarjetas de "Destinos" (sol y mar, metrópolis,
aire libre, a medida) y los 4 destinos de "A medida" ya tienen la foto real
que mandó la agencia, guardadas en `src/agencia/web/estatico/img/destinos/`
y `.../img/internacionales/` respectivamente. Los 4 flyers nacionales de
"Salidas grupales" usan sus fotos en `.../img/flyers/`; los 2 internacionales
de ejemplo (Punta Cana, Viña del Mar) todavía no tienen foto propia y
reutilizan dos de las de "Destinos" — están marcados con
`<!-- COMPLETAR -->` para reemplazarlas cuando haya una foto real del viaje.
Para cambiar una foto o agregar un viaje nuevo, se suma el archivo en la
carpeta que corresponda y se apunta el `src` del `<img>` — se suben directo
al repo, no se enlazan a un sitio externo (un intento anterior con fotos de
Wikimedia Commons no se veía en el sitio publicado).

**Fotos livianas para celular:** cada `<img>` de una foto de viaje va
envuelto en un `<picture>` con una fuente `.webp` (25–40% más liviana que
el `.jpg` al lado, mismo tamaño) que el navegador prueba primero, cayendo
al `.jpg` si no la soporta. La del hero, además, tiene `srcset` con cuatro
anchos (480/800/1280/1717px): un celular baja la de 480px en vez de la
foto completa de 456 KB. Si cambiás o agregás una foto, hay que generar
su `.webp` al lado (incluidos los tres anchos extra si es la del hero) —
no hay paso de build que lo haga solo. Alcanza con:

```python
from PIL import Image
im = Image.open("la-foto.jpg").convert("RGB")
im.save("la-foto.webp", "WEBP", quality=82)
```

(`pillow` no es una dependencia del sistema — hace falta instalarla aparte
para correr esto, `pip install pillow`.)

**"Salidas grupales" vs "A medida":** son dos secciones con la misma
tarjeta (`.tarjeta-flyer`), pero un botón distinto a propósito. Una salida
grupal —nacional o internacional, con mayorista o propia— tiene fecha, cupo
y precio cerrado, así que el botón cobra directo con Mercado Pago. Un viaje
a medida no tiene fecha fija: depende del tipo de cambio y la disponibilidad
del día, así que lleva un precio "Desde U$S X" de referencia y el botón abre
WhatsApp para pedir la cotización exacta.

**Itinerario de cada salida grupal:** cada flyer de "Salidas grupales"
tiene, debajo del botón de pago, un link **"Ver itinerario completo"** que
lleva a su propia página (`itinerario-bariloche.html`, `itinerario-iguazu.html`,
`itinerario-mendoza.html`, `itinerario-calafate.html`, `itinerario-punta-cana.html`,
`itinerario-vina-del-mar.html`, en las rutas `/salidas-grupales/<destino>`)
con el día por día, horarios, y qué incluye y qué no. Para una salida nueva:
copiar uno de esos archivos, agregarlo a `PAGINAS_PUBLICAS` en `rutas.py`
con su ruta, y linkearlo desde la tarjeta correspondiente en
`salidas-grupales.html` (y opcionalmente desde el resumen en `publico.html`)
con la clase `flyer-mas-info`.

### Cobros con Mercado Pago (sección "Salidas grupales")

Cada flyer tiene un botón **"Pagar con Mercado Pago"**. Es un link fijo, no
una integración con API: no requiere ninguna clave ni tocar el servidor, y
funciona igual en local y en Vercel. Para activar el cobro de un viaje real:

1. Entrá a tu cuenta de Mercado Pago → **Tu negocio → Cobros → Links de
   pago** (o "Cobrar" → "Crear link de pago").
2. Cargá el nombre del viaje y el precio (ahí también se define si se
   permite pagar en cuotas).
3. Copiá la URL que te da Mercado Pago y pegala en el `href` del botón
   correspondiente en `salidas-grupales.html` (donde hoy dice `href="#"`) y
   en su página de itinerario (`itinerario-<destino>.html`, mismo botón
   repetido al final de la página).

Con eso, el pasajero paga con tarjeta de crédito o débito directamente en
Mercado Pago; la agencia ve el cobro en su propia cuenta como cualquier otro
link de pago. Si en algún momento hace falta que la página sepa
automáticamente si un viaje ya se pagó (por ejemplo para bajarlo solo de la
web cuando se agotan los cupos), eso requiere pasar a una integración con la
API de Mercado Pago y guardar un Access Token como variable de entorno —
hoy no está implementado.

---

## Puesta en marcha

Hay dos maneras de usarlo y el sistema funciona igual en las dos.

### Publicado en Vercel

1. Entrá a [vercel.com](https://vercel.com), creá una cuenta e importá este
   repositorio ("Add New… → Project").
2. **Elegí la rama correcta.** Vercel despliega `main` por defecto. Si el código
   está en otra rama, andá a *Settings → Git → Production Branch*, escribí el
   nombre de esa rama y guardá; después *Deployments → Redeploy*. Si el proyecto
   aparece creado pero no carga, esto suele ser la causa.
3. Dale **Deploy** y esperá un minuto.
4. Te queda una dirección para entrar desde cualquier lado, también del celular.

Si el deploy falla, abrí el deployment en Vercel y mirá los **Build Logs**: el
error concreto está ahí. Y aunque el sistema no llegue a arrancar, esta
dirección responde igual y dice qué falta:

```
https://tu-proyecto.vercel.app/api/estado
```

### Si las facturas dicen "no instalado" pese a tener `requirements.txt`

`vercel.json` tiene que declarar `builds` con `"use": "@vercel/python"` — es
lo que le dice a Vercel que instale `requirements.txt`. Sin esa línea, la
función arranca igual (por eso la página puede llegar a cargar) pero corre
con un intérprete pelado, sin ninguna librería instalada. No se puede
combinar `builds` con `functions` en el mismo archivo — Vercel rechaza esa
mezcla —, así que las demás opciones (`maxLambdaSize`, `includeFiles`) van
adentro de `builds[0].config`, no en un bloque `functions` aparte.

### Si el build falla por tamaño del paquete ("exceeds the maximum function size")

`includeFiles` en `builds[0].config` tiene que apuntar solo a lo que la
función necesita en tiempo de ejecución (`src/` y `config/`), nunca a `"**"`.
Con `"**"` se arrastran también los archivos que Vercel genera durante su
propio proceso de instalación (`.venv`, `build/`, `uv.lock` y similares),
duplicando el tamaño del paquete final muy por encima del límite. `pymupdf`
por sí solo pesa unos 65 MB (la librería C de MuPDF compilada); todas las
dependencias juntas rondan los 100 MB, bien por debajo del límite — el
problema nunca fue el peso de las librerías, sino qué más se estaba
empaquetando de más.

### Si el diagnóstico dice que faltan todas las librerías por igual

El instalador de Python de Vercel usa `uv`, no `pip` directo, y `uv` resuelve
las dependencias desde `pyproject.toml` (`[project] dependencies`), **no**
desde `requirements.txt`. Si `pyproject.toml` las tiene como opcionales o con
`dependencies = []`, `uv` instala exactamente eso: nada — y las cuatro
librerías fallan por igual, sin que ninguna tenga un error de compilación de
por medio. `requirements.txt` se mantiene solo como referencia para quien
instale con `pip` directamente; hay que mantener las dos listas iguales a
mano.

### Si todo da 404, incluida la página principal

Con `builds`, la función queda publicada en la ruta exacta de su archivo
fuente, **con la extensión incluida**: `/api/index.py`, no `/api/index`. Es
distinto de como se comporta `functions` (zero-config), que sí le saca el
`.py`. Por eso el archivo enruta con `routes` (el formato viejo, `src`/`dest`,
que es el que acompaña a `builds`) apuntando a `/api/index.py` con la
extensión puesta — no con `rewrites`, que en este proyecto apuntaba al lugar
equivocado y hacía que todo el sitio devolviera 404 de la propia plataforma
(no un 404 de la aplicación).

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

La primera vez, entrá a `/panel` → **Mayoristas** y cargá:

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
| `SMTP_HOST` | Servidor SMTP para mandar el formulario de contacto por correo. Sin esto, el formulario cae al `mailto:` del navegador. |
| `SMTP_PUERTO` | Puerto del servidor SMTP (587 por defecto, con STARTTLS). |
| `SMTP_USUARIO` | Usuario para autenticarse en el SMTP (y remitente del correo). |
| `SMTP_CLAVE` | Contraseña o clave de aplicación de ese usuario. |
| `CONTACTO_EMAIL` | A dónde llega cada consulta (`hola@esplora.com.ar` por defecto). |

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
