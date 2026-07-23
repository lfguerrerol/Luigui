# 📈 FBA Arbitrage Finder

Sistema para **retail arbitrage en Amazon FBA**: busca productos con descuento en
tiendas (Walmart, Target, Home Depot, Costco, Sam's Club), los cruza con datos de
Amazon (Keepa, Helium 10, Jungle Scout, SellerAmp), calcula la rentabilidad real
(tarifas FBA incluidas) y arma una **lista de sourcing que alcanza tu meta de
ganancia mensual** con el margen que definas.

Funciona **sin claves API** usando un catálogo de muestra, para que puedas
probarlo de inmediato. Cuando agregues las claves reales, cambia a datos en vivo.

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
│   ├── models.py              # modelos Pydantic (productos, ofertas, filtros)
│   ├── fba_calculator.py      # tarifas FBA + motor de rentabilidad
│   ├── engine.py              # escaneo + filtros + lista de sourcing
│   ├── sample_data.py         # catálogo de muestra (funciona sin API keys)
│   └── connectors/
│       ├── base.py            # interfaces de conectores
│       ├── retailers.py       # Walmart, Target, Home Depot, Costco, Sam's
│       ├── analytics.py       # Keepa, Helium 10, Jungle Scout, SellerAmp
│       ├── keepa_client.py    # cliente EN VIVO de Keepa (precio, rank, ventas)
│       └── junglescout_client.py  # cliente EN VIVO de Jungle Scout (estimación de ventas)
└── frontend/
    └── index.html             # dashboard React (vía CDN, sin build)
```

### Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard (React) |
| GET | `/api/config` | Estado de conectores (vivo vs. muestra) |
| POST | `/api/scan` | Escaneo con filtros (cuerpo `ScanFilters`) |
| GET | `/api/deals` | Igual que scan pero con query params |
| POST | `/api/analyze` | Analiza un producto individual |
| GET | `/api/health` | Healthcheck |

---

## 🔌 Conectar datos reales (APIs)

Cada conector se activa poniendo su variable de entorno. Mientras no exista,
usa el catálogo de muestra automáticamente.

```bash
# Tiendas
export WALMART_API_KEY=...        # Walmart Affiliate / Marketplace API
export TARGET_API_KEY=...         # RedCircle u otro feed
export HOMEDEPOT_API_KEY=...
export COSTCO_API_KEY=...
export SAMSCLUB_API_KEY=...

# Análisis de Amazon
export KEEPA_API_KEY=...          # ✅ YA IMPLEMENTADO (en vivo)
export KEEPA_DOMAIN=1             # opcional: 1=amazon.com, 2=.co.uk, 3=.de ...
export HELIUM10_API_KEY=...       # estimación de ventas (stub)
export JUNGLESCOUT_API_KEY=...    # ✅ YA IMPLEMENTADO (en vivo)
export JUNGLESCOUT_KEY_NAME=...   # nombre de clave que acompaña a la API key
export JUNGLESCOUT_MARKETPLACE=us # opcional (default us)
export SELLERAMP_API_KEY=...      # (stub)
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

Para los demás proveedores, implementa el método correspondiente:
- Tiendas → `_fetch_live()` en `connectors/retailers.py`
- Análisis → `lookup()` en `connectors/analytics.py` (usa `keepa_client.py` como modelo)

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
