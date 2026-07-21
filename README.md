# 📊 Procurement Dashboard (FLEX Shopping List)

Streamlit dashboard estilo **Fab Tracker** para dar seguimiento a compras,
presupuesto y tiempos de entrega (ETA).

## Novedades

- **Sección Fixtures & Gauges** — se carga automáticamente desde la hoja
  `FIXTURES & GAUGES` (o `Fixtures` / `Gauges`) del template de Excel y se
  suma a KPIs, presupuesto, status y tablas de detalle.
- **Formato tipo Fab Tracker** — header con gradiente, tarjetas KPI, colores
  de status (PO / IN PROCESS / PENDING) y gráficas con Altair.
- **Modo Día / Noche** — selector en la barra lateral con paletas afinadas
  para ambos contrastes.
- **Columna ETA** — tiempo de entrega. En el template va **después de
  `Status` y antes de `Comments`**. Acepta días (número) o una fecha de
  entrega (se convierte a días restantes).
- **Top 10 tiempos de entrega más largos** — gráfica horizontal ubicada
  **debajo de Procurement Status** y **a un lado de Budget vs Spend**.

## Columnas esperadas en el template

```
ITEM | Supplier | Supplier code | Image | Description | Qty | IT | ASSY |
Unit cost USD | Total Cost USD | CODE | REQ | Total real | Status | PO |
ETA | Comments
```

> La detección del encabezado busca la fila que contiene `Total Cost USD`,
> así que puede vivir unas filas debajo del inicio de la hoja.

## Uso

```bash
pip install -r requirements.txt
streamlit run Shopping_List.py
```

Luego sube el archivo Excel (template) desde la interfaz.

## Imágenes de ítems

`extract_images.py` extrae las imágenes embebidas del Excel a
`images/<categoria>/<ITEM>.jpg` (incluye la carpeta `fixtures`). Coloca el
template junto al script o define `EXCEL_PATH`:

```bash
EXCEL_PATH="/ruta/Shopping list.xlsx" python extract_images.py
```
