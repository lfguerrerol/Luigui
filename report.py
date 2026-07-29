"""Landscape (16:9) presentation-style PDF report for the Procurement Dashboard.

Builds a small slide deck (cover, executive summary, status + ETA, top costs
and one detail-table section per category) with matplotlib so it works
headless — no browser required.
"""

import datetime
import io
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ---- Brand palette (print-friendly: light slides, colored accents) ----
NAVY = "#0f172a"
BLUE = "#2563eb"
INDIGO = "#4f46e5"
SLATE = "#64748b"
CARD = "#f8fafc"
BORDER = "#e2e8f0"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#dc2626"
WHITE = "#ffffff"

FIGSIZE = (13.33, 7.5)  # 16:9 presentation
CAT_COLORS = ["#2563eb", "#0891b2", "#7c3aed", "#0ea5e9", "#f59e0b", "#14b8a6"]
ROWS_PER_PAGE = 15  # detail table rows before spilling to a new slide

# Columns shown in the detail tables (label, relative width)
DETAIL_COLS = [
    ("ITEM", 0.05),
    ("Description", 0.30),
    ("Supplier", 0.15),
    ("Qty", 0.06),
    ("Total Cost USD", 0.13),
    ("Capex/NRE", 0.10),
    ("Status", 0.13),
    ("ETA", 0.08),
]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _new_slide(facecolor=WHITE):
    fig = plt.figure(figsize=FIGSIZE)
    fig.patch.set_facecolor(facecolor)
    return fig


def _footer(fig, page, total):
    fig.text(0.04, 0.03, "FLEX · Procurement Dashboard", color=SLATE, fontsize=8)
    fig.text(0.96, 0.03, f"{page} / {total}", color=SLATE, fontsize=8, ha="right")


def _title(fig, text):
    fig.text(0.04, 0.9, text, color=NAVY, fontsize=22, fontweight="bold")
    ax = fig.add_axes([0.04, 0.87, 0.14, 0.006])
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, color=BLUE, transform=ax.transAxes))


def _truncate(s, n=34):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _find(df, name):
    """Case-insensitive column lookup."""
    for c in df.columns:
        if str(c).strip().lower() == name.lower():
            return c
    return None


def _tiles(fig, rect, items):
    ax = fig.add_axes(rect)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    n = len(items)
    gap = 0.012
    w = (1 - gap * (n - 1)) / n
    for i, (label, val, accent) in enumerate(items):
        x = i * (w + gap)
        ax.add_patch(Rectangle((x, 0), w, 1, facecolor=CARD, edgecolor=BORDER,
                               linewidth=1))
        ax.add_patch(Rectangle((x, 0), 0.008, 1, color=accent))
        ax.text(x + 0.02, 0.66, label, fontsize=8.5, color=SLATE,
                fontweight="bold")
        ax.text(x + 0.02, 0.26, val, fontsize=13.5, color=NAVY,
                fontweight="bold")


def _style_table(table, status_col=None, cell_text=None):
    """Apply the shared header/zebra styling (+ optional Status coloring)."""
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(BORDER)
        if r == 0:
            cell.set_facecolor(NAVY)
            cell.set_text_props(color=WHITE, fontweight="bold")
        else:
            cell.set_facecolor(CARD if r % 2 else WHITE)
            cell.set_text_props(color=NAVY)
            if status_col is not None and c == status_col and cell_text is not None:
                txt = str(cell_text[r - 1][status_col]).lower()
                if "po" in txt:
                    cell.set_text_props(color=GREEN, fontweight="bold")
                elif "process" in txt:
                    cell.set_text_props(color=AMBER, fontweight="bold")
                elif txt.strip() not in ("", "—"):
                    cell.set_text_props(color=RED, fontweight="bold")


# ---------------------------------------------------------------------------
# SLIDES
# ---------------------------------------------------------------------------
def _cover(pdf, d, page, npages):
    fig = _new_slide(NAVY)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    ax.add_patch(Rectangle((0, 0), 1, 0.12, color=BLUE))
    ax.add_patch(Rectangle((0, 0.12), 1, 0.012, color=INDIGO))

    logo = d.get("logo")
    if logo and os.path.exists(logo):
        try:
            img = plt.imread(logo)
            la = fig.add_axes([0.76, 0.78, 0.18, 0.14])
            la.axis("off")
            la.imshow(img)
        except Exception:
            pass

    ax.text(0.06, 0.74, "PROCUREMENT DASHBOARD", color=WHITE,
            fontsize=34, fontweight="bold")
    ax.text(0.06, 0.67, "Executive Report · Fixtures & Gauges · ETA Tracking",
            color="#94a3b8", fontsize=15)

    ax.text(0.06, 0.42, f"${d['total_all']:,.0f}", color=WHITE,
            fontsize=54, fontweight="bold")
    ax.text(0.065, 0.36, "TOTAL SPEND", color="#94a3b8", fontsize=13,
            fontweight="bold")

    delta = d["delta"]
    if delta > 0:
        ax.text(0.06, 0.26, f"▲ Over Budget  +${delta:,.0f}", color="#f87171",
                fontsize=18, fontweight="bold")
    else:
        ax.text(0.06, 0.26, f"▼ Under Budget  ${delta:,.0f}", color="#4ade80",
                fontsize=18, fontweight="bold")
    ax.text(0.065, 0.205, f"Budget: ${d['budget']:,.0f}", color="#94a3b8",
            fontsize=12)

    ax.text(0.06, 0.05, datetime.date.today().strftime("%B %d, %Y"),
            color="#cbd5e1", fontsize=12, fontweight="bold")

    pdf.savefig(fig, facecolor=fig.get_facecolor())
    plt.close(fig)


def _summary(pdf, d, page, npages):
    fig = _new_slide()
    _title(fig, "Executive Summary")

    totals = d["totals"]
    items = [("TOTAL SPEND", f"${d['total_all']:,.0f}", INDIGO)]
    for i, (label, val) in enumerate(totals.items()):
        items.append((label, f"${val:,.0f}", CAT_COLORS[i % len(CAT_COLORS)]))
    _tiles(fig, [0.04, 0.62, 0.92, 0.2], items)

    ax = fig.add_axes([0.08, 0.12, 0.84, 0.4])
    cats = list(totals.keys())
    vals = list(totals.values())
    order = sorted(range(len(vals)), key=lambda k: vals[k], reverse=True)
    cats = [cats[i] for i in order]
    vals = [vals[i] for i in order]
    colors = [CAT_COLORS[i % len(CAT_COLORS)] for i in range(len(cats))]
    bars = ax.bar(cats, vals, color=colors, width=0.6)
    ax.set_ylabel("USD", color=SLATE, fontsize=10)
    ax.set_title("Spend by Category", color=NAVY, fontsize=13,
                 fontweight="bold", loc="left")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.tick_params(colors=SLATE, labelsize=9)
    ax.grid(axis="y", color=BORDER, linewidth=0.7)
    ax.set_axisbelow(True)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"${v:,.0f}",
                ha="center", va="bottom", fontsize=8, color=NAVY,
                fontweight="bold")

    _footer(fig, page, npages)
    pdf.savefig(fig, facecolor=fig.get_facecolor())
    plt.close(fig)


def _status_eta(pdf, d, page, npages):
    fig = _new_slide()
    _title(fig, "Procurement Status & Delivery Times")

    status = d["status"]
    _tiles(
        fig,
        [0.04, 0.66, 0.92, 0.16],
        [
            ("PO  ·  COMPLETED", str(status["PO"]), GREEN),
            ("IN PROCESS", str(status["IN PROCESS"]), AMBER),
            ("PENDING", str(status["PENDING"]), RED),
        ],
    )

    ax = fig.add_axes([0.30, 0.1, 0.62, 0.46])
    eta = d["top_eta"]
    if eta is not None and len(eta):
        items = list(eta["Item"])[::-1]
        days = list(eta["ETA (days)"])[::-1]
        ax.barh(range(len(items)), days, color=RED, alpha=0.85, height=0.6)
        ax.set_yticks(range(len(items)))
        ax.set_yticklabels([_truncate(i, 30) for i in items], fontsize=8.5,
                           color=NAVY)
        ax.set_xlabel("Delivery lead time (days)", color=SLATE, fontsize=10)
        ax.set_title("Top 10 Longest Delivery Times (ETA)", color=NAVY,
                     fontsize=13, fontweight="bold", loc="left")
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.tick_params(colors=SLATE, labelsize=8)
        ax.grid(axis="x", color=BORDER, linewidth=0.7)
        ax.set_axisbelow(True)
        for i, v in enumerate(days):
            ax.text(v, i, f" {v:.0f}", va="center", fontsize=8, color=NAVY,
                    fontweight="bold")
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "Agrega la columna ETA en el template\n"
                          "(después de Status y antes de Comments)",
                ha="center", va="center", color=SLATE, fontsize=12)

    _footer(fig, page, npages)
    pdf.savefig(fig, facecolor=fig.get_facecolor())
    plt.close(fig)


def _top_costs(pdf, d, page, npages):
    fig = _new_slide()
    _title(fig, "Top 10 Cost Items")

    df = d["top_cost"]
    ax = fig.add_axes([0.04, 0.06, 0.92, 0.78])
    ax.axis("off")

    if df is None or df.empty:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", color=SLATE)
    else:
        cols = ["#", "Description", "Category", "Cost (USD)", "Status"]
        cell_text = []
        for rank, (_, row) in enumerate(df.iterrows(), start=1):
            cell_text.append([
                str(rank),
                _truncate(row.get("Description", ""), 40),
                _truncate(row.get("Category", ""), 18),
                f"${row.get('Total Cost USD', 0):,.0f}",
                _truncate(row.get("Status", "") or "—", 14),
            ])
        table = ax.table(cellText=cell_text, colLabels=cols, cellLoc="left",
                         loc="center",
                         colWidths=[0.05, 0.42, 0.19, 0.17, 0.17])
        table.auto_set_font_size(False)
        table.set_fontsize(9.5)
        table.scale(1, 1.9)
        _style_table(table, status_col=4, cell_text=cell_text)

    _footer(fig, page, npages)
    pdf.savefig(fig, facecolor=fig.get_facecolor())
    plt.close(fig)


def _detail_value(name, value):
    if name == "Total Cost USD":
        try:
            return f"${float(value):,.0f}"
        except (ValueError, TypeError):
            return str(value)
    if name == "Qty":
        try:
            return f"{float(value):g}"
        except (ValueError, TypeError):
            return _truncate(value, 8)
    if name == "Description":
        return _truncate(value, 44)
    if name == "Supplier":
        return _truncate(value, 20)
    if name in ("Status", "Capex/NRE"):
        s = str(value).strip()
        return s if s else "—"
    return _truncate(value, 16)


def _category_slides(pdf, title, df, page, npages):
    """Render one (or more) detail-table slides for a single category."""
    cols, widths = [], []
    for name, w in DETAIL_COLS:
        real = _find(df, name)
        if real is not None:
            cols.append((name, real))
            widths.append(w)
    total_w = sum(widths)
    widths = [w / total_w for w in widths]

    header = [c[0] for c in cols]
    status_col = header.index("Status") if "Status" in header else None
    n_pages = max(1, math.ceil(len(df) / ROWS_PER_PAGE))

    for p in range(n_pages):
        sub = df.iloc[p * ROWS_PER_PAGE:(p + 1) * ROWS_PER_PAGE]
        fig = _new_slide()
        suffix = f"  ({p + 1}/{n_pages})" if n_pages > 1 else ""
        _title(fig, f"Detail · {title}{suffix}")

        ax = fig.add_axes([0.03, 0.05, 0.94, 0.80])
        ax.axis("off")

        cell_text = [[_detail_value(name, row.get(real, "")) for name, real in cols]
                     for _, row in sub.iterrows()]

        table = ax.table(cellText=cell_text, colLabels=header, cellLoc="left",
                         loc="upper center", colWidths=widths)
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        table.scale(1, 1.5)
        _style_table(table, status_col=status_col, cell_text=cell_text)

        _footer(fig, page, npages)
        pdf.savefig(fig, facecolor=fig.get_facecolor())
        plt.close(fig)
        page += 1

    return page


# ---------------------------------------------------------------------------
# PUBLIC
# ---------------------------------------------------------------------------
def _count_pages(d):
    n = 4  # cover, summary, status+eta, top costs
    for df in d.get("details", {}).values():
        if df is not None and not df.empty:
            n += max(1, math.ceil(len(df) / ROWS_PER_PAGE))
    return n


def build_report_pdf(d):
    """Build the report and return it as PDF bytes.

    `d` keys: totals(dict), total_all, budget, delta, status(dict),
    top_eta(DataFrame|None), top_cost(DataFrame|None), logo(path|None),
    details(dict label -> DataFrame, optional).
    """
    from matplotlib.backends.backend_pdf import PdfPages

    buf = io.BytesIO()
    npages = _count_pages(d)
    page = 1
    with PdfPages(buf) as pdf:
        _cover(pdf, d, page, npages); page += 1
        _summary(pdf, d, page, npages); page += 1
        _status_eta(pdf, d, page, npages); page += 1
        _top_costs(pdf, d, page, npages); page += 1
        for label, df in d.get("details", {}).items():
            if df is None or df.empty:
                continue
            page = _category_slides(pdf, label, df, page, npages)
    buf.seek(0)
    return buf.getvalue()
