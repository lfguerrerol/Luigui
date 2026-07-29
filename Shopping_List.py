import os
import subprocess
import sys

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

from report import build_report_pdf

st.set_page_config(
    page_title="Procurement Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Base directory of this script -> makes image/logo paths portable
BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# Purchase type classification
CLASS_COL = "Capex/NRE"
CLASS_OPTIONS = ["Capex", "NRE"]


def open_path(path):
    """Open a local folder in the OS file explorer.

    Only works when the app runs on the same machine as the browser
    (e.g. localhost). Returns (ok, message).
    """
    if not path:
        return False, "Ruta vacía."
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return False, f"No existe la ruta: {path}"
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # noqa: S606 (Windows only)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
        return True, f"Abriendo: {folder}"
    except Exception as e:  # pragma: no cover
        return False, f"No se pudo abrir la carpeta: {e}"

# =============================
# THEME / CONTRAST  (Fab Tracker style)
# =============================
# Discreet: the sidebar starts collapsed and this control is pushed to the
# very bottom so it stays out of the way.
st.sidebar.markdown("<div style='height:68vh'></div>", unsafe_allow_html=True)
st.sidebar.caption("Ajustes")
contrast = st.sidebar.radio(
    "Contraste visual",
    ["Día", "Noche"],
    index=0,
    key="visual_contrast",
    horizontal=True,
    label_visibility="collapsed",
)

if contrast == "Noche":
    THEME = {
        "bg": "#0b1220",
        "bg2": "#0f172a",
        "text": "#f1f5f9",
        "muted": "#94a3b8",
        "card": "#111c33",
        "card2": "#0f1a2e",
        "border": "#243350",
        "accent": "#38bdf8",
        "accent2": "#22d3ee",
        "grad_a": "#0ea5e9",
        "grad_b": "#6366f1",
        "ok": "#22c55e",
        "ok_bg": "#0f2a1c",
        "warn": "#f59e0b",
        "warn_bg": "#2a2110",
        "bad": "#ef4444",
        "bad_bg": "#2a1416",
        "grid": "#1e293b",
    }
else:
    THEME = {
        "bg": "#f4f6fb",
        "bg2": "#ffffff",
        "text": "#0f172a",
        "muted": "#64748b",
        "card": "#ffffff",
        "card2": "#f8fafc",
        "border": "#e2e8f0",
        "accent": "#2563eb",
        "accent2": "#0891b2",
        "grad_a": "#2563eb",
        "grad_b": "#7c3aed",
        "ok": "#16a34a",
        "ok_bg": "#dcfce7",
        "warn": "#d97706",
        "warn_bg": "#fef3c7",
        "bad": "#dc2626",
        "bad_bg": "#fee2e2",
        "grid": "#e2e8f0",
    }

# =============================
# STYLE
# =============================
st.markdown(
    f"""
<style>
:root {{
    --bg: {THEME['bg']};
    --bg2: {THEME['bg2']};
    --text: {THEME['text']};
    --muted: {THEME['muted']};
    --card: {THEME['card']};
    --card2: {THEME['card2']};
    --border: {THEME['border']};
    --accent: {THEME['accent']};
    --accent2: {THEME['accent2']};
    --grad-a: {THEME['grad_a']};
    --grad-b: {THEME['grad_b']};
    --ok: {THEME['ok']};
    --warn: {THEME['warn']};
    --bad: {THEME['bad']};
}}

.stApp {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
}}

section[data-testid="stSidebar"] {{
    background-color: var(--card) !important;
    border-right: 1px solid var(--border);
}}

/* Streamlit's fixed top toolbar -> keep it transparent so the page bg
   shows through, and push our content below it so the logo/header don't
   get clipped by it. */
[data-testid="stHeader"] {{
    background: transparent !important;
}}
.block-container {{ padding-top: 4.5rem; }}

h1, h2, h3, h4, h5, h6, p, span, label {{ color: var(--text); }}

/* ---- Hero header ---- */
.hero {{
    background: linear-gradient(120deg, var(--grad-a), var(--grad-b));
    border-radius: 16px;
    padding: 18px 26px;
    color: #ffffff;
    box-shadow: 0 8px 24px rgba(0,0,0,0.18);
}}
.hero h1 {{ color:#fff; margin:0; font-size:2rem; letter-spacing:.5px; }}
.hero p  {{ color:rgba(255,255,255,.85); margin:.2rem 0 0 0; font-weight:500; }}

/* ---- KPI cards ---- */
[data-testid="stMetric"] {{
    background: linear-gradient(160deg, var(--card), var(--card2));
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    padding: 16px 18px;
    border-radius: 14px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.06);
}}
[data-testid="stMetricLabel"] {{ color: var(--muted) !important; font-weight:600; }}
[data-testid="stMetricValue"] {{ color: var(--text) !important; }}

[data-testid="stDataFrame"] {{
    background-color: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
}}

div[data-testid="stExpander"] {{
    background-color: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.05);
    overflow: hidden;
}}
div[data-testid="stExpander"] summary {{ font-weight:700; font-size:1.02rem; }}
div[data-testid="stExpander"] button {{ color: var(--text); }}

.stAlert, .stSuccess, .stError, .stWarning {{ border-radius: 10px; }}

/* status pills */
.pill {{
    display:inline-block; padding:2px 10px; border-radius:999px;
    font-size:.78rem; font-weight:700;
}}
</style>
""",
    unsafe_allow_html=True,
)

# =============================
# HEADER
# =============================
col1, col2 = st.columns([1, 8])

with col1:
    logo_path = os.path.join(BASE_PATH, "Logo_Flex.jpg")
    if os.path.exists(logo_path):
        st.image(Image.open(logo_path), width=140)

with col2:
    st.markdown(
        "<div class='hero'>"
        "<h1>📊 PROCUREMENT DASHBOARD</h1>"
        "<p>Executive Overview · Fixtures &amp; Gauges · ETA Tracking</p>"
        "</div>",
        unsafe_allow_html=True,
    )

st.write("")

# =============================
# CATEGORY DEFINITION
# =============================
# (label, list of sheet-name keywords to match, image folder)
CATEGORIES = [
    ("ASSY", ["assy"], "assy"),
    ("QA TOOLING", ["qa tooling", "qa"], "qa"),
    ("INSERTION", ["insertion"], "insertion"),
    ("AUTOMATION", ["automation"], "automation"),
    ("FIXTURES & GAUGES", ["fixtures & gauges", "fixtures", "gauges", "gauge", "fixture"], "fixtures"),
]

# =============================
# FILE
# =============================
file = st.file_uploader("Upload Excel File", type=["xlsx"])

if not file:
    st.info("⬆️ Sube el archivo Excel (template) para generar el dashboard.")
    st.stop()

xls = pd.ExcelFile(file)


def resolve_sheet(keywords):
    """Return the first sheet name that matches one of the keywords."""
    for kw in keywords:
        for s in xls.sheet_names:
            if kw.lower() in s.lower():
                return s
    return None


# =============================
# CLEAN
# =============================
def load_clean(sheet):
    if sheet is None:
        return pd.DataFrame()

    df = pd.read_excel(xls, sheet_name=sheet, header=None)

    header_idx = None
    for i in range(min(12, len(df))):
        row = df.iloc[i].astype(str).str.lower()
        if "total cost usd" in row.values:
            header_idx = i
            break

    if header_idx is None:
        return pd.DataFrame()

    df.columns = df.iloc[header_idx]
    df = df[header_idx + 1:]

    df = df.dropna(how="all")
    df = df[~df.astype(str).apply(lambda x: x.str.contains("total", case=False)).any(axis=1)]
    df = df.fillna("")

    # normalise column labels (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    if "Total Cost USD" in df.columns:
        df["Total Cost USD"] = pd.to_numeric(df["Total Cost USD"], errors="coerce")
        df = df[df["Total Cost USD"].notna()]
        df = df[df["Total Cost USD"] > 0]

    return df


# ---- Load every category ----
data = {}
for label, keywords, folder in CATEGORIES:
    data[label] = load_clean(resolve_sheet(keywords))


def find_col(df, name):
    """Case-insensitive column lookup."""
    for c in df.columns:
        if str(c).strip().lower() == name.lower():
            return c
    return None


# =============================
# ETA HELPERS  (delivery lead time, expressed in weeks)
# =============================
def eta_weeks(df):
    """Return delivery lead time in WEEKS, aligned to df.index.

    Handles the ETA column whether it is a plain number (days), a delivery
    date, or an Excel duration — always yielding sensible weeks instead of
    the nanosecond blow-up you get from feeding datetimes to to_numeric.
    Missing/invalid -> NaN.
    """
    if df.empty:
        return pd.Series(dtype=float)

    col = find_col(df, "ETA")
    if col is None:
        return pd.Series([float("nan")] * len(df), index=df.index)

    s = df[col].replace("", pd.NA)

    if pd.api.types.is_timedelta64_dtype(s):
        # An actual duration -> days
        days = s.dt.total_seconds() / 86400.0
    elif pd.api.types.is_datetime64_any_dtype(s):
        # A delivery date -> remaining days from today
        days = (s - pd.Timestamp.today().normalize()).dt.days
    else:
        # Object/text column: plain numbers are lead-time days; anything
        # that is really a date gets converted from its date value.
        days = pd.to_numeric(s, errors="coerce")
        missing = days.isna() & s.notna()
        if missing.any():
            dates = pd.to_datetime(s[missing], errors="coerce")
            days.loc[missing] = (dates - pd.Timestamp.today().normalize()).dt.days

    days = pd.to_numeric(days, errors="coerce")
    return (days / 7.0).round(1)


def collect_eta(data):
    """Build a DataFrame of every item with a valid ETA (in weeks)."""
    rows = []
    for label, df in data.items():
        if df.empty:
            continue
        weeks = eta_weeks(df)
        desc_col = find_col(df, "Description")
        for idx in df.index:
            w = weeks.get(idx, float("nan"))
            if pd.notna(w):
                rows.append({
                    "Item": str(df.loc[idx, desc_col]) if desc_col else str(idx),
                    "Category": label,
                    "ETA (weeks)": float(w),
                })
    return pd.DataFrame(rows)


def collect_cost(data):
    """Concatenate all categories (adding a Category column) for ranking."""
    frames = []
    for label, df in data.items():
        if df.empty:
            continue
        d = df.copy()
        d["Category"] = label
        frames.append(d)
    return pd.concat(frames) if frames else pd.DataFrame()


# =============================
# CAPEX / NRE CLASSIFICATION
# =============================
def _norm_class(v):
    s = str(v).strip().lower()
    if s in ("capex", "cap", "c"):
        return "Capex"
    if s in ("nre", "n"):
        return "NRE"
    if "cap" in s:
        return "Capex"
    if "nre" in s:
        return "NRE"
    return ""


def init_classification(data):
    """Seed the session store from a template column (if any), once per item."""
    store = st.session_state.setdefault("capex_nre", {})
    for label, df in data.items():
        tcol = None
        for cand in ("Capex/NRE", "Capex / NRE", "CAPEX/NRE", "Type", "Tipo"):
            c = find_col(df, cand)
            if c is not None:
                tcol = c
                break
        for idx in df.index:
            key = f"{label}#{idx}"
            if key not in store:
                store[key] = _norm_class(df.loc[idx, tcol]) if tcol is not None else ""
    return store


def apply_classification(data, store):
    """Write the current classification back into each category DataFrame."""
    for label, df in data.items():
        df[CLASS_COL] = [store.get(f"{label}#{idx}", "") for idx in df.index]


# =============================
# KPI
# =============================
totals = {label: (df["Total Cost USD"].sum() if "Total Cost USD" in df.columns else 0.0)
          for label, df in data.items()}
total_all = sum(totals.values())

budget = 2176956
delta = total_all - budget

st.subheader("💵 EXECUTIVE SUMMARY")

# Seed classification (from template / prior edits) so TOTAL SPEND can be
# split into Capex vs NRE right here.
class_store = init_classification(data)
apply_classification(data, class_store)


def _fmt_compact(v):
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


cap_kpi = nre_kpi = 0.0
for _df in data.values():
    if _df.empty:
        continue
    _cost = pd.to_numeric(_df["Total Cost USD"], errors="coerce").fillna(0)
    _cls = _df[CLASS_COL].astype(str)
    cap_kpi += float(_cost[_cls == "Capex"].sum())
    nre_kpi += float(_cost[_cls == "NRE"].sum())

kpi_cols = st.columns(len(CATEGORIES) + 1)
kpi_cols[0].metric("TOTAL SPEND", f"${total_all:,.0f}")
kpi_cols[0].caption(f"🏗️ Capex {_fmt_compact(cap_kpi)} · 🔧 NRE {_fmt_compact(nre_kpi)}")
for i, (label, _, _) in enumerate(CATEGORIES, start=1):
    kpi_cols[i].metric(label, f"${totals[label]:,.0f}")

# =============================
# STATUS SUMMARY
# =============================
def status_summary(df):
    col = find_col(df, "Status")
    if col is not None and not df.empty:
        s = df[col].astype(str).str.lower()
        po = int(s.str.contains("po").sum())
        inproc = int(s.str.contains("process").sum())
        pending = len(df) - int(s.str.contains("po|process").sum())
        return {"PO": po, "IN PROCESS": inproc, "PENDING": pending}
    return {"PO": 0, "IN PROCESS": 0, "PENDING": len(df)}


status_totals = {"PO": 0, "IN PROCESS": 0, "PENDING": 0}
for df in data.values():
    s = status_summary(df)
    for k in status_totals:
        status_totals[k] += s[k]

# =============================
# PRE-COMPUTE RANKINGS (shared by dashboard + PDF)
# =============================
eta_all = collect_eta(data)
top10_eta = (eta_all.sort_values("ETA (weeks)", ascending=False).head(10)
             if not eta_all.empty else eta_all)

cost_all = collect_cost(data)
top10_cost = (cost_all.sort_values("Total Cost USD", ascending=False).head(10)
              if not cost_all.empty else cost_all)

# =============================
# EXPORT TO PDF (placeholder — filled at the end so it reflects live edits)
# =============================
_, exp_r = st.columns([3, 1])
export_slot = exp_r.empty()

# =============================
# ROW: BUDGET (left)  ||  STATUS + ETA TOP-10 (right)
# =============================
col_left, col_right = st.columns(2)

# -------- BUDGET vs SPEND ----------
with col_left:
    with st.expander("💰 Budget vs Spend", expanded=True):
        if delta > 0:
            st.error(f"Over Budget: +${delta:,.0f}")
        else:
            st.success(f"Under Budget: ${delta:,.0f}")

        chart_df = pd.DataFrame(
            {"Category": list(totals.keys()), "Cost": list(totals.values())}
        )
        bar = (
            alt.Chart(chart_df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("Category:N", sort="-y", title=None,
                        axis=alt.Axis(labelAngle=-20, labelColor=THEME["text"])),
                y=alt.Y("Cost:Q", title="USD", axis=alt.Axis(labelColor=THEME["muted"])),
                color=alt.Color("Category:N", legend=None,
                                scale=alt.Scale(scheme="tealblues")),
                tooltip=["Category", alt.Tooltip("Cost:Q", format="$,.0f")],
            )
            .properties(height=300, background="transparent")
        )
        st.altair_chart(bar, use_container_width=True)

# -------- STATUS + ETA TOP 10 ----------
with col_right:
    with st.expander("🚦 Procurement Status", expanded=True):
        s1, s2, s3 = st.columns(3)
        s1.metric("✅ PO", status_totals["PO"])
        s2.metric("🟡 IN PROCESS", status_totals["IN PROCESS"])
        s3.metric("🔴 PENDING", status_totals["PENDING"])

    with st.expander("⏱️ Top 10 Longest Delivery Times (ETA)", expanded=True):
        if not top10_eta.empty:
            eta_chart = (
                alt.Chart(top10_eta)
                .mark_bar(cornerRadiusEnd=6)
                .encode(
                    y=alt.Y("Item:N", sort="-x", title=None,
                            axis=alt.Axis(labelColor=THEME["text"], labelLimit=180)),
                    x=alt.X("ETA (weeks):Q", title="Delivery lead time (weeks)",
                            axis=alt.Axis(labelColor=THEME["muted"])),
                    color=alt.Color("ETA (weeks):Q", legend=None,
                                    scale=alt.Scale(scheme="orangered")),
                    tooltip=["Item", "Category", "ETA (weeks)"],
                )
                .properties(height=300, background="transparent")
            )
            st.altair_chart(eta_chart, use_container_width=True)
        else:
            st.info("Agrega la columna **ETA** (después de *Status* y antes de "
                    "*Comments*) en el template para ver los tiempos de entrega.")

# =============================
# INSIGHTS
# =============================
with st.expander("🧠 Key Insights", expanded=True):
    if total_all > 0:
        top_cat = max(totals.items(), key=lambda x: x[1])
        pct = (top_cat[1] / total_all) * 100
        st.write(f"• **{top_cat[0]}** represents **{pct:.1f}%** of total spend.")
    st.write(
        f"• Procurement pipeline: **{status_totals['PO']}** PO · "
        f"**{status_totals['IN PROCESS']}** in process · "
        f"**{status_totals['PENDING']}** pending."
    )

# =============================
# TOP 10 COST ITEMS
# =============================
with st.expander("🔝 Top 10 Cost Items", expanded=True):
    if not top10_cost.empty:
        st.dataframe(top10_cost, use_container_width=True)

# =============================
# CAPEX / NRE CLASSIFICATION (editable)
# =============================
with st.expander("🏷️ Capex vs NRE", expanded=True):
    st.caption("Selecciona el tipo de compra por ítem. Se guarda durante la "
               "sesión y se refleja en las tablas de detalle y en el PDF.")

    labels = [c[0] for c in CATEGORIES]
    cls_tabs = st.tabs(labels)
    for tab, label in zip(cls_tabs, labels):
        with tab:
            df = data[label]
            if df.empty:
                st.info("Sin datos para esta categoría.")
                continue

            desc_col = find_col(df, "Description")
            view = pd.DataFrame({
                "Description": (df[desc_col].astype(str) if desc_col
                                else df.index.astype(str)),
                "Total Cost USD": pd.to_numeric(df["Total Cost USD"],
                                                errors="coerce"),
                CLASS_COL: [class_store.get(f"{label}#{idx}", "")
                            for idx in df.index],
            })
            view.index = df.index

            edited = st.data_editor(
                view,
                key=f"cls_editor_{label}",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Description": st.column_config.TextColumn(
                        "Description", disabled=True),
                    "Total Cost USD": st.column_config.NumberColumn(
                        "Total Cost USD", format="$%.0f", disabled=True),
                    CLASS_COL: st.column_config.SelectboxColumn(
                        "Capex / NRE", options=CLASS_OPTIONS, required=False,
                        help="Capex = inversión de capital · NRE = non-recurring"),
                },
            )
            for idx, val in zip(edited.index, edited[CLASS_COL]):
                class_store[f"{label}#{idx}"] = "" if val is None else str(val)

    # write selections back into the working data
    apply_classification(data, class_store)

    # ---- Capex vs NRE summary ----
    cap_total = nre_total = unclassified = 0.0
    cap_n = nre_n = 0
    for df in data.values():
        if df.empty:
            continue
        cost = pd.to_numeric(df["Total Cost USD"], errors="coerce").fillna(0)
        cls = df[CLASS_COL].astype(str)
        cap_total += float(cost[cls == "Capex"].sum())
        nre_total += float(cost[cls == "NRE"].sum())
        unclassified += float(cost[~cls.isin(CLASS_OPTIONS)].sum())
        cap_n += int((cls == "Capex").sum())
        nre_n += int((cls == "NRE").sum())

    m1, m2, m3 = st.columns(3)
    m1.metric("🏗️ CAPEX", f"${cap_total:,.0f}", f"{cap_n} ítems")
    m2.metric("🔧 NRE", f"${nre_total:,.0f}", f"{nre_n} ítems")
    m3.metric("❔ Sin clasificar", f"${unclassified:,.0f}")

    if cap_total + nre_total > 0:
        cap_df = pd.DataFrame({
            "Tipo": ["Capex", "NRE"],
            "USD": [cap_total, nre_total],
        })
        cap_chart = (
            alt.Chart(cap_df)
            .mark_bar(cornerRadiusEnd=6)
            .encode(
                x=alt.X("USD:Q", title="USD", axis=alt.Axis(labelColor=THEME["muted"])),
                y=alt.Y("Tipo:N", title=None, axis=alt.Axis(labelColor=THEME["text"])),
                color=alt.Color("Tipo:N", legend=None,
                                scale=alt.Scale(domain=["Capex", "NRE"],
                                                range=["#2563eb", "#f59e0b"])),
                tooltip=["Tipo", alt.Tooltip("USD:Q", format="$,.0f")],
            )
            .properties(height=140, background="transparent")
        )
        st.altair_chart(cap_chart, use_container_width=True)

# =============================
# ARCHIVOS Y RUTAS (abrir carpetas locales)
# =============================
with st.expander("🗂️ Rutas y archivos (abrir carpetas)", expanded=False):
    st.caption("Abre carpetas en el explorador de tu equipo. Solo funciona "
               "cuando ejecutas la app localmente (localhost).")

    base_dir = st.text_input("Carpeta base del proyecto", value=BASE_PATH,
                             key="base_dir_input")

    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("📂 Abrir carpeta de imágenes", use_container_width=True):
            ok, msg = open_path(os.path.join(base_dir, "images"))
            (st.success if ok else st.warning)(msg)
    with rc2:
        if st.button("📂 Abrir carpeta base", use_container_width=True):
            ok, msg = open_path(base_dir)
            (st.success if ok else st.warning)(msg)

    excel_dir = st.text_input(
        "Ruta del Excel (Shopping List) — carpeta o archivo .xlsx",
        value="", key="excel_dir_input",
        placeholder=r"Ej. C:\Users\tuusuario\...\FLEX Shopping List\Shopping list.xlsx",
    )
    if st.button("📂 Abrir carpeta del Excel", use_container_width=True):
        ok, msg = open_path(excel_dir or base_dir)
        (st.success if ok else st.warning)(msg)

# =============================
# STATUS COLORING FOR TABLES
# =============================
def style_status(df):
    col = find_col(df, "Status")
    if col is None:
        return df

    def _color(val):
        v = str(val).lower()
        if "po" in v:
            return f"background-color:{THEME['ok_bg']}; color:{THEME['ok']}; font-weight:700;"
        if "process" in v:
            return f"background-color:{THEME['warn_bg']}; color:{THEME['warn']}; font-weight:700;"
        if v.strip() == "":
            return ""
        return f"background-color:{THEME['bad_bg']}; color:{THEME['bad']}; font-weight:700;"

    return df.style.applymap(_color, subset=[col])


# =============================
# DETAILED TABLES + IMAGES
# =============================
with st.expander("📋 Detailed Tables", expanded=False):

    labels = [c[0] for c in CATEGORIES]
    folders = {c[0]: c[2] for c in CATEGORIES}
    tabs = st.tabs(labels)

    def show_table(df, title, folder):
        st.subheader(title)

        if df.empty:
            st.info("Sin datos para esta categoría en el archivo.")
            return

        st.dataframe(style_status(df), use_container_width=True)

        if title not in st.session_state:
            st.session_state[title] = df.index[0]

        desc_col = find_col(df, "Description")
        idx = st.selectbox(
            f"Select item ({title})",
            df.index,
            index=list(df.index).index(st.session_state[title]),
            key=f"select_{title}",
            format_func=lambda x: str(df.loc[x, desc_col]) if desc_col else str(x),
        )

        if st.checkbox(f"Show Item Detail ({title})", key=f"chk_{title}"):
            row = df.loc[idx]
            st.markdown("### 🔍 Item Detail")

            c_img, c_info = st.columns([1, 2])

            with c_img:
                item_col = find_col(df, "ITEM") or find_col(df, "Item")
                item_id = str(row.get(item_col, idx)).replace(".0", "").strip() if item_col else str(idx)
                folder_path = os.path.join(BASE_PATH, "images", folder)
                image_path = os.path.join(folder_path, f"{item_id}.jpg")
                st.caption(image_path)
                if os.path.exists(image_path):
                    st.image(Image.open(image_path), use_container_width=True)
                else:
                    st.warning(f"Image not found: {item_id}.jpg")
                if st.button("📂 Abrir carpeta de imágenes",
                             key=f"openimg_{title}", use_container_width=True):
                    ok, msg = open_path(folder_path)
                    (st.success if ok else st.warning)(msg)

            with c_info:
                current_pos = list(df.index).index(idx)
                nav1, _, nav3 = st.columns([1, 2, 1])
                with nav1:
                    if st.button("⬅️ Previous", key=f"prev_{title}") and current_pos > 0:
                        st.session_state[title] = df.index[current_pos - 1]
                        st.rerun()
                with nav3:
                    if st.button("Next ➡️", key=f"next_{title}") and current_pos < len(df.index) - 1:
                        st.session_state[title] = df.index[current_pos + 1]
                        st.rerun()

                st.markdown("---")

                fields = list(df.columns)
                mid = len(fields) // 2
                colL, colR = st.columns(2)
                with colL:
                    for f in fields[:mid]:
                        st.markdown(f"<b>{f}:</b> {row[f]}", unsafe_allow_html=True)
                with colR:
                    for f in fields[mid:]:
                        st.markdown(f"<b>{f}:</b> {row[f]}", unsafe_allow_html=True)

    for tab, label in zip(tabs, labels):
        with tab:
            show_table(data[label], label, folders[label])

# =============================
# BUILD PDF (now that classification is applied) -> fill the top button
# =============================
def compute_capex(data):
    cap = nre = unc = 0.0
    cap_n = nre_n = unc_n = 0
    by_category = []
    for label, df in data.items():
        if df.empty or CLASS_COL not in df.columns:
            continue
        cost = pd.to_numeric(df["Total Cost USD"], errors="coerce").fillna(0)
        cls = df[CLASS_COL].astype(str)
        c = float(cost[cls == "Capex"].sum())
        n = float(cost[cls == "NRE"].sum())
        u = float(cost[~cls.isin(CLASS_OPTIONS)].sum())
        cap += c; nre += n; unc += u
        cap_n += int((cls == "Capex").sum())
        nre_n += int((cls == "NRE").sum())
        unc_n += int((~cls.isin(CLASS_OPTIONS)).sum())
        by_category.append((label, c, n))
    return {
        "cap_total": cap, "nre_total": nre, "unclassified": unc,
        "cap_n": cap_n, "nre_n": nre_n, "unclassified_n": unc_n,
        "by_category": by_category,
    }


try:
    pdf_bytes = build_report_pdf({
        "totals": totals,
        "total_all": total_all,
        "budget": budget,
        "delta": delta,
        "status": status_totals,
        "top_eta": top10_eta,
        "top_cost": top10_cost,
        "logo": logo_path,
        "details": data,
        "capex": compute_capex(data),
    })
    export_slot.download_button(
        "⬇️ Exportar reporte PDF",
        data=pdf_bytes,
        file_name="Procurement_Report.pdf",
        mime="application/pdf",
        use_container_width=True,
        help="Genera un reporte tipo presentación (horizontal) para dirección.",
    )
except Exception as e:  # pragma: no cover - never break the dashboard
    export_slot.warning(f"No se pudo generar el PDF: {e}")
