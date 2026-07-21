import os

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

st.set_page_config(page_title="Procurement Dashboard", layout="wide")

# Base directory of this script -> makes image/logo paths portable
BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# =============================
# THEME / CONTRAST  (Fab Tracker style)
# =============================
contrast = st.sidebar.radio(
    "Contraste visual",
    ["Día", "Noche"],
    index=0,
    key="visual_contrast",
    horizontal=True,
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

.block-container {{ padding-top: 1.2rem; }}

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
# ETA HELPERS  (delivery lead time)
# =============================
def eta_days(df):
    """Return a numeric Series (days of delivery lead time) aligned to df.index.

    Accepts either a numeric lead time or a delivery date; dates are
    converted to remaining days from today. Missing/invalid -> NaN.
    """
    if df.empty:
        return pd.Series(dtype=float)

    col = find_col(df, "ETA")
    if col is None:
        return pd.Series([float("nan")] * len(df), index=df.index)

    raw = df[col].replace("", pd.NA)

    # Prefer plain numeric lead times.
    num = pd.to_numeric(raw, errors="coerce")

    # For anything not numeric, try to read it as a delivery date and
    # convert to remaining days from today.
    missing = num.isna() & raw.notna()
    if missing.any():
        dates = pd.to_datetime(raw[missing], errors="coerce")
        day_from_date = (dates - pd.Timestamp.today().normalize()).dt.days
        num.loc[missing] = day_from_date

    return pd.to_numeric(num, errors="coerce")


# =============================
# KPI
# =============================
totals = {label: (df["Total Cost USD"].sum() if "Total Cost USD" in df.columns else 0.0)
          for label, df in data.items()}
total_all = sum(totals.values())

budget = 2176956
delta = total_all - budget

st.subheader("💵 EXECUTIVE SUMMARY")

kpi_cols = st.columns(len(CATEGORIES) + 1)
kpi_cols[0].metric("TOTAL SPEND", f"${total_all:,.0f}")
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
        eta_rows = []
        for label, df in data.items():
            if df.empty:
                continue
            days = eta_days(df)
            desc_col = find_col(df, "Description")
            for idx in df.index:
                d = days.get(idx, float("nan"))
                if pd.notna(d):
                    eta_rows.append(
                        {
                            "Item": str(df.loc[idx, desc_col]) if desc_col else str(idx),
                            "Category": label,
                            "ETA (days)": float(d),
                        }
                    )

        if eta_rows:
            eta_df = (
                pd.DataFrame(eta_rows)
                .sort_values("ETA (days)", ascending=False)
                .head(10)
            )
            eta_chart = (
                alt.Chart(eta_df)
                .mark_bar(cornerRadiusEnd=6)
                .encode(
                    y=alt.Y("Item:N", sort="-x", title=None,
                            axis=alt.Axis(labelColor=THEME["text"], labelLimit=180)),
                    x=alt.X("ETA (days):Q", title="Delivery lead time (days)",
                            axis=alt.Axis(labelColor=THEME["muted"])),
                    color=alt.Color("ETA (days):Q", legend=None,
                                    scale=alt.Scale(scheme="orangered")),
                    tooltip=["Item", "Category", "ETA (days)"],
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
    non_empty = [d for d in data.values() if not d.empty]
    if non_empty:
        combined = pd.concat(non_empty)
        top10 = combined.sort_values(by="Total Cost USD", ascending=False).head(10)
        st.dataframe(top10, use_container_width=True)

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
                image_path = os.path.join(BASE_PATH, "images", folder, f"{item_id}.jpg")
                st.caption(image_path)
                if os.path.exists(image_path):
                    st.image(Image.open(image_path), use_container_width=True)
                else:
                    st.warning(f"Image not found: {item_id}.jpg")

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
