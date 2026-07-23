# 🔑 Cómo llenar las claves API en el `.env`

Guía para conectar tus claves reales al **FBA Arbitrage Finder**. No necesitas
todas — abajo se marca el **mínimo recomendado** para empezar.

---

## Primer paso

```bash
cd fba_arbitrage
cp .env.example .env
nano .env      # o ábrelo con tu editor favorito
```

**Reglas:**
- Formato `VARIABLE=valor`, **sin comillas ni espacios** alrededor del `=`.
- Deja en blanco las variables que no tengas (esos conectores usarán datos de muestra).
- Guarda el archivo y reinicia la app para que tome los cambios.

---

## 🟢 Mínimo recomendado para empezar

Con solo estas dos ya tienes un sistema funcional (datos de Amazon + ofertas de tiendas).

### 1. Keepa — datos de Amazon (precio, sales rank, ventas) ⭐ la más importante

- **Dónde:** [keepa.com](https://keepa.com) → Login → **API** (de pago, por tokens).
- Copia tu API key del panel.

```
KEEPA_API_KEY=tu_clave_de_keepa_aqui
KEEPA_DOMAIN=1                # 1=amazon.com (USA), 2=.co.uk, 3=.de, 4=.fr, 5=.co.jp
KEEPA_MATCH_THRESHOLD=0.35    # déjalo así (similitud de título cuando no hay UPC)
```

### 2. SerpApi — ofertas de Home Depot, Target, Costco, Sam's Club

- **Dónde:** [serpapi.com](https://serpapi.com) → Register → Dashboard → **"Your Private API Key"**.
- Tiene plan gratuito (100 búsquedas/mes) para probar.

```
SERPAPI_KEY=tu_clave_de_serpapi_aqui
SERPAPI_QUERIES=clearance,open box    # qué buscar (puedes cambiarlo)
```

---

## 🔵 Opcionales (agrégalas cuando las tengas)

### 3. Jungle Scout — estimación de ventas (necesita **2 valores**)

- **Dónde:** [developer.junglescout.com](https://developer.junglescout.com) (requiere plan con API access).
  Al crear una API key te dan un **nombre** y un **secreto**.

```
JUNGLESCOUT_API_KEY=el_secreto
JUNGLESCOUT_KEY_NAME=el_nombre_de_la_clave    # ⚠️ ambos son obligatorios
JUNGLESCOUT_MARKETPLACE=us
```

### 4. Walmart — API oficial (firma RSA, necesita 2 cosas)

- **Dónde:** [walmart.io](https://walmart.io) → regístrate como developer → crea una app.
  Te dan un **Consumer ID** y subes una **clave pública**; tú guardas la **privada** (`.pem`).

```
WALMART_CONSUMER_ID=tu_consumer_id
WALMART_PRIVATE_KEY_FILE=/ruta/completa/a/tu/walmart_private.pem
WALMART_KEY_VERSION=1
WALMART_QUERIES=clearance,rollback
```

> Aquí se pone la **ruta al archivo** `.pem`, no la clave en sí.
> Ej: `/home/tu_usuario/keys/walmart_private.pem`.
> (Alternativamente puedes pegar el PEM en línea con `WALMART_PRIVATE_KEY=`.)

### 5. Helium 10 y SellerAmp — estimación de ventas

- No tienen API pública abierta (son de nivel enterprise). Si tu plan te da acceso,
  te darán una clave y una **URL de endpoint**, que pones en `_API_URL`.

```
HELIUM10_API_KEY=tu_clave
HELIUM10_API_URL=https://la_url_real_de_tu_endpoint
HELIUM10_MARKETPLACE=US

SELLERAMP_API_KEY=tu_clave
SELLERAMP_API_URL=https://la_url_real_de_tu_endpoint
```

---

## Ejemplo de `.env` mínimo ya lleno

```
KEEPA_API_KEY=abc123keepatoken
KEEPA_DOMAIN=1
KEEPA_MATCH_THRESHOLD=0.35
SERPAPI_KEY=xyz789serpapikey
SERPAPI_QUERIES=clearance,open box
```

---

## Verificar que quedó bien

```bash
python run.py
```

Abre **http://localhost:8020/api/config** — los conectores que llenaste deben
mostrar `"live": true`. Si ves `false`:

- Revisa que la clave no tenga espacios ni comillas.
- Confirma que reiniciaste la app después de editar `.env`.
- Para Jungle Scout, recuerda que necesita **ambos** valores (`API_KEY` y `KEY_NAME`).

---

## 🔒 Seguridad (importante)

- Llena el `.env` **en tu máquina**, nunca pegues tus claves en un chat o issue.
- `.env` está en `.gitignore` — **nunca** lo subas al repositorio. Solo se
  versiona la plantilla `.env.example` (sin secretos).
- Si alguna vez expones una clave por error, **revócala/regenérala** en el panel
  del proveedor de inmediato.

---

## Resumen de conectores

| Conector | Variables | ¿Obligatorio? |
|----------|-----------|---------------|
| **Keepa** | `KEEPA_API_KEY` (+ opcionales) | Recomendado ⭐ |
| **SerpApi** | `SERPAPI_KEY` | Recomendado ⭐ |
| **Jungle Scout** | `JUNGLESCOUT_API_KEY` + `JUNGLESCOUT_KEY_NAME` | Opcional |
| **Walmart** | `WALMART_CONSUMER_ID` + `WALMART_PRIVATE_KEY_FILE` | Opcional |
| **Helium 10** | `HELIUM10_API_KEY` + `HELIUM10_API_URL` | Opcional |
| **SellerAmp** | `SELLERAMP_API_KEY` + `SELLERAMP_API_URL` | Opcional |

Sin ninguna clave, el sistema funciona con **datos de muestra** para que puedas
probarlo de inmediato.
