# 📈 FBA Arbitrage Finder

Sistema para **retail arbitrage en Amazon FBA**: busca productos con descuento en
tiendas (Walmart, Target, Home Depot, Costco, Sam's Club), los cruza con datos de
Amazon (Keepa, Helium 10, Jungle Scout, SellerAmp), calcula la rentabilidad real
(tarifas FBA incluidas) y arma una **lista de sourcing que alcanza tu meta de
ganancia mensual** con el margen que definas.

Funciona **sin claves API** usando un catálogo de muestra, para que puedas
probarlo de inmediato. Cuando agregues las claves reales, cambia a datos en vivo.
El dashboard también funciona **offline** (React/Babel vienen incluidos, sin CDN).

### Dashboard

- Barra de **progreso hacia la meta** mensual.
- **Gráfica** de las mejores ofertas por ganancia proyectada/mes.
- Tabla **ordenable** por cualquier columna (margen, ROI, ganancia, ventas…).
- **Favoritos** persistentes (se guardan en el navegador) y filtro "solo favoritos".
- **Exportar a CSV** las ofertas para tu lista de compras.
- Pestaña **Calculadora** para analizar un producto manualmente.
- Pestaña **Tarifas FBA** para editar referral fees por categoría, almacenamiento
  y costos por unidad; se guardan en el servidor y afectan todos los cálculos.

---

## 🚀 Cómo ejecutarlo

```bash
cd fba_arbitrage
pip install -r requirements.txt
python run.py
```

Abre **http://localhost:8020**

---

## 🎯 El filtro que pediste

En la pestaña **Buscador de ofertas** defines:

| Campo | Ejemplo | Qué hace |
|-------|---------|----------|
| **Meta de ganancia mensual** | `$1000` | Objetivo de ganancia por mes |
| **Margen mínimo** | `15%` | Solo muestra ofertas con margen ≥ este valor |
| ROI mínimo | `0%` | Retorno sobre la inversión mínimo |
| Ganancia mínima por unidad | `$2` | Descarta ofertas de ganancia muy baja |
| Ventas mensuales mínimas | `0` | Filtra por velocidad de venta (Keepa/Helium10) |
| % de ventas que capturas | `0.30` | Cuota realista frente a otros vendedores |

El sistema:
1. Calcula **ganancia neta por unidad** (precio Amazon − compra − tarifas FBA − envío − prep).
2. Proyecta la **ganancia mensual** = ganancia/unidad × (ventas del listado × tu captura).
3. Ordena las ofertas y construye la **lista de sourcing recomendada** que suma
   hasta llegar a tu meta (`$1000/mes`), indicando cuántas unidades necesitas.

También hay una pestaña **Calculadora** para analizar un producto manualmente.

---

## 🧩 Arquitectura

```
fba_arbitrage/
├── run.py                     # arranca el servidor (puerto 8020)
├── requirements.txt
├── backend/
│   ├── main.py                # API FastAPI + sirve el frontend
│   ├── env_loader.py          # carga las claves desde .env al arrancar
│   ├── models.py              # modelos Pydantic (productos, ofertas, filtros)
│   ├── fba_calculator.py      # tarifas FBA + motor de rentabilidad
│   ├── engine.py              # escaneo + filtros + lista de sourcing
│   ├── settings.py            # tarifas FBA editables (persistidas en JSON)
│   ├── sample_data.py         # catálogo de muestra (funciona sin API keys)
│   └── connectors/
│       ├── base.py            # interfaces de conectores
│       ├── retailers.py       # Walmart, Target, Home Depot, Costco, Sam's
│       ├── analytics.py       # Keepa, Helium 10, Jungle Scout, SellerAmp
│       ├── keepa_client.py    # cliente EN VIVO de Keepa (precio, rank, ventas)
│       ├── junglescout_client.py  # cliente EN VIVO de Jungle Scout (ventas)
│       ├── walmart_client.py  # cliente EN VIVO de Walmart.io (firma RSA)
│       ├── serpapi_client.py  # tiendas sin API oficial vía SerpApi
│       ├── helium10_client.py # enriquecedor de ventas (contrato configurable)
│       ├── selleramp_client.py# enriquecedor de ventas (contrato configurable)
│       └── category_map.py    # mapea categorías de tienda -> categorías FBA
└── frontend/
    ├── index.html             # dashboard React (sin build)
    └── vendor/                # React + Babel locales (funciona offline, sin CDN)
```

### Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard (React) |
| GET | `/api/config` | Estado de conectores (vivo vs. muestra) |
| POST | `/api/scan` | Escaneo con filtros (cuerpo `ScanFilters`) |
| GET | `/api/deals` | Igual que scan pero con query params |
| POST | `/api/analyze` | Analiza un producto individual |
| GET | `/api/settings` | Tarifas FBA actuales (defaults + overrides) |
| PUT | `/api/settings` | Actualiza y guarda tarifas (validado) |
| POST | `/api/settings/reset` | Restaura tarifas por defecto |
| GET | `/api/health` | Healthcheck |

---

## 🔌 Conectar datos reales (APIs)

> 📘 Guía paso a paso de dónde sacar cada clave y cómo llenarla:
> [`docs/CONFIGURAR_API.md`](docs/CONFIGURAR_API.md)

### Forma recomendada: archivo `.env`

```bash
cd fba_arbitrage
cp .env.example .env      # copia la plantilla
nano .env                 # pega tus claves reales (solo las que tengas)
python run.py             # la app carga .env automáticamente
```

Luego abre **http://localhost:8020/api/config** y verifica que los conectores que
configuraste muestren `"live": true`.

> 🔒 **Seguridad:** `.env` está en `.gitignore` — **nunca** lo subas al repo ni
> pegues tus claves en un chat/issue. La plantilla `.env.example` (sin secretos)
> sí se versiona. Deja en blanco los conectores que no tengas: seguirán usando
> datos de muestra.

Cada conector se activa poniendo su variable. Alternativamente puedes exportarlas
en tu shell en vez de usar `.env`:

```bash
# Tiendas
# Walmart (API OFICIAL, ya implementada — firma RSA)
export WALMART_CONSUMER_ID=...        # tu Consumer ID de walmart.io
export WALMART_PRIVATE_KEY_FILE=...   # ruta al PEM de tu clave privada RSA
#   (o WALMART_PRIVATE_KEY con el PEM en línea)
export WALMART_KEY_VERSION=1          # opcional (default 1)
export WALMART_QUERIES="clearance,rollback"  # opcional: términos a buscar

# Home Depot / Target / Costco / Sam's (SIN API oficial -> vía agregador SerpApi)
export SERPAPI_KEY=...                # https://serpapi.com
export SERPAPI_QUERIES="clearance,open box"  # opcional

# Análisis de Amazon
export KEEPA_API_KEY=...          # ✅ YA IMPLEMENTADO (en vivo)
export KEEPA_DOMAIN=1             # opcional: 1=amazon.com, 2=.co.uk, 3=.de ...
export KEEPA_MATCH_THRESHOLD=0.35 # opcional: similitud mínima de título (sin UPC)
export JUNGLESCOUT_API_KEY=...    # ✅ estimación de ventas (API pública)
export JUNGLESCOUT_KEY_NAME=...   # nombre de clave que acompaña a la API key
export JUNGLESCOUT_MARKETPLACE=us # opcional (default us)
export HELIUM10_API_KEY=...       # ✅ implementado (contrato configurable, ver nota)
export HELIUM10_API_URL=...       # opcional: URL real de tu endpoint Helium 10
export SELLERAMP_API_KEY=...      # ✅ implementado (contrato configurable, ver nota)
export SELLERAMP_API_URL=...      # opcional: URL real de tu endpoint SellerAmp
```

### Jungle Scout en vivo (ya funciona)

Jungle Scout se usa como **refinador de estimación de ventas**: su API devuelve
unidades vendidas por día para un ASIN, pero no el precio. Por eso el flujo es:
Keepa/muestra aportan precio + rank + rating (con el ASIN) y Jungle Scout
**reemplaza `est_monthly_sales`** con su estimación (su especialidad), etiquetando
el proveedor como `Keepa+JungleScout`. Necesita `JUNGLESCOUT_API_KEY` **y**
`JUNGLESCOUT_KEY_NAME`. Si falla cae al valor previo sin romper el escaneo.
Implementación: `connectors/junglescout_client.py`.

### Keepa en vivo (ya funciona)

Con `KEEPA_API_KEY` configurada, el sistema consulta la API real de Keepa por
UPC de cada producto y trae: precio Buy Box / New, sales rank, **ventas
estimadas del mes** (`monthlySold`), rating, número de reseñas, cantidad de
vendedores y si Amazon vende en el listado. Si una consulta falla (sin tokens,
red, etc.) cae automáticamente a datos de muestra sin romper el escaneo.
Implementación: `connectors/keepa_client.py`.

### Tiendas en vivo (ya funcionan)

Cascada por tienda (usa el primero disponible, si no cae a datos de muestra):

| Tienda | Fuente en vivo | Notas |
|--------|----------------|-------|
| **Walmart** | API oficial `walmart.io` (firma RSA) → o SerpApi | Única con API oficial |
| **Home Depot** | SerpApi (motor `home_depot`) | Sin API pública oficial |
| **Target** | SerpApi (Google Shopping, filtrado por tienda) | Sin API pública oficial |
| **Costco** | SerpApi (Google Shopping, filtrado por tienda) | Sin API pública oficial |
| **Sam's Club** | SerpApi (Google Shopping, filtrado por tienda) | Sin API pública oficial |

Implementación: `connectors/walmart_client.py` y `connectors/serpapi_client.py`.
El mapeo de respuestas está centralizado en las funciones `parse_*`, así que
puedes cambiar SerpApi por otro agregador (BlueCart, Rainforest, Traject Data)
editando un solo lugar. El mapeo de categorías de cada tienda a las categorías
de tarifas FBA está en `connectors/category_map.py`.

> **Google Shopping y el emparejamiento sin UPC:** Google Shopping no expone
> UPC. Para no perder esas ofertas (Target/Costco/Sam's), cuando un producto no
> trae UPC el cliente de Keepa lo **busca por título** (endpoint `/search`) y
> acepta el mejor resultado **solo si el título es suficientemente similar**
> (similitud de tokens ≥ `KEEPA_MATCH_THRESHOLD`, default 0.35), para evitar
> emparejar con el listado equivocado. Estos matches se etiquetan como
> `Keepa (título)`. Los motores de Walmart y Home Depot sí devuelven
> identificadores más ricos y se emparejan por código.

### Enriquecedores de ventas: Jungle Scout, Helium 10, SellerAmp

Keepa/muestra aportan precio + rank + rating; luego el **primer enriquecedor
configurado** (en orden: Jungle Scout → Helium 10 → SellerAmp) reemplaza la
estimación de ventas y etiqueta el proveedor (`Keepa+Helium10`, etc.). Solo se
aplica uno (una fuente de ventas autoritativa basta).

> **Nota honesta sobre Helium 10 y SellerAmp:** a diferencia de Keepa y Jungle
> Scout (APIs públicas documentadas), Helium 10 y SellerAmp **no publican una
> API abierta para suscriptores normales** (son de nivel enterprise/gated). Sus
> clientes (`helium10_client.py`, `selleramp_client.py`) apuntan a un contrato
> razonable con la **URL configurable** (`HELIUM10_API_URL`, `SELLERAMP_API_URL`)
> y el **mapeo de respuesta centralizado** en `parse_units()`, para que ajustes
> el endpoint y los campos a tu cuenta real sin tocar el resto del sistema. El
> `parse_units` ya tolera varios nombres de campo comunes.

La estructura de datos ya está definida en `models.py`, así que solo tienes que
mapear la respuesta de cada API a `RetailProduct` / `AmazonInsight`.

---

## 💰 Cómo se calculan las tarifas FBA

`fba_calculator.py` incluye tablas aproximadas de Amazon US (2024/2025):
- **Referral fee** por categoría (8%–17%, mínimo $0.30).
- **Fulfillment fee** por peso/tamaño.
- **Almacenamiento** por pie cúbico.
- Envío inbound + prep configurables.

Los valores son ajustables; verifica siempre las tarifas vigentes en Seller
Central antes de comprar inventario real.

---

## ⚠️ Nota

Los precios y ventas del catálogo de muestra son ilustrativos. Este sistema es
una herramienta de análisis de sourcing: valida cada oferta con datos reales
(Keepa/SellerAmp) y las políticas de marca/gating de Amazon antes de comprar.
