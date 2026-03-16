"""
Amex → Zapro Supplier Reconciliation  |  Streamlit App
=======================================================
Solution 3 of 3 — Browser-based reconciliation tool.

Features:
  • Login / session management
  • Upload Amex XLS + Suppliers JSON (or use bundled samples)
  • Configurable match threshold + live alias table editor
  • Colour-coded results table with summary KPI cards
  • One-click download of formatted reconciliation Excel

Run:
    streamlit run app.py
"""

import io
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import xlrd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz, process

# ── Page config (must be first Streamlit call) ────────────────────────────
st.set_page_config(
    page_title="Amex Reconciliation",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────

VALID_USERS = {
    "admin": "foxx2026",
    "finance": "recon123",
}

DEFAULT_ALIASES = [
    {"From": "SQSP",        "To": "Squarespace"},
    {"From": "AMZN",        "To": "Amazon"},
    {"From": "HOMEDEPOT",   "To": "home depot"},
    {"From": "HOME DEPOT",  "To": "home depot"},
    {"From": "B2B PRIME",   "To": "Amazon"},
    {"From": "DISCOUNTTO",  "To": "DiscountToday"},
    {"From": "SP TRUDOOR",  "To": "Trudoor"},
    {"From": "LOWES",       "To": "Lowes"},
    {"From": "STAPLES",     "To": "Staples"},
    {"From": "RAPIDAPI",    "To": "RapidAPI"},
    {"From": "AUTH0",       "To": "Auth0"},
    {"From": "JOTFORM",     "To": "JotForm"},
    {"From": "NMSDC",       "To": "NMSDC"},
]

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC",
}

COLOURS = {
    "AUTO MATCH": "#C6EFCE",
    "REVIEW":     "#FFEB9C",
    "NOT FOUND":  "#FFC7CE",
}

XLSX_COLOURS = {
    "AUTO MATCH": "C6EFCE",
    "REVIEW":     "FFEB9C",
    "NOT FOUND":  "FFC7CE",
    "header":     "1F3864",
    "subheader":  "2F75B6",
}

AMEX_DESC_COL  = 6
SKIP_KEYWORDS  = {"REMITTANCE", "PAYMENT", "BALANCE"}


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────

def inject_css():
    st.markdown("""
    <style>
    /* ── Fonts ─────────────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

    /* ── Root palette ───────────────────────────────────────────────── */
    :root {
        --navy:   #1F3864;
        --blue:   #2F75B6;
        --lblue:  #E8F1FA;
        --green:  #C6EFCE;
        --amber:  #FFEB9C;
        --red:    #FFC7CE;
        --ink:    #1a1a2e;
        --muted:  #6B7280;
        --border: #E5E7EB;
        --bg:     #F8FAFC;
    }

    /* ── Global ─────────────────────────────────────────────────────── */
    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        background-color: var(--bg);
        color: var(--ink);
    }

    /* ── Hide default Streamlit chrome ──────────────────────────────── */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    /* ── Login card ─────────────────────────────────────────────────── */
    .login-wrap {
        max-width: 420px;
        margin: 6rem auto 0;
        background: white;
        border-radius: 16px;
        padding: 3rem;
        box-shadow: 0 4px 32px rgba(31,56,100,.10);
        border: 1px solid var(--border);
    }
    .login-logo {
        font-family: 'DM Serif Display', serif;
        font-size: 1.9rem;
        color: var(--navy);
        margin-bottom: .25rem;
    }
    .login-sub {
        font-size: .85rem;
        color: var(--muted);
        margin-bottom: 2rem;
    }

    /* ── Top header bar ─────────────────────────────────────────────── */
    .app-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: .75rem 1.5rem;
        background: var(--navy);
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .app-header-title {
        font-family: 'DM Serif Display', serif;
        font-size: 1.35rem;
        color: white;
        flex: 1;
    }
    .app-header-user {
        font-size: .8rem;
        color: rgba(255,255,255,.65);
        font-family: 'DM Mono', monospace;
    }

    /* ── KPI cards ──────────────────────────────────────────────────── */
    .kpi-grid { display: flex; gap: 1rem; margin-bottom: 1.25rem; }
    .kpi-card {
        flex: 1;
        background: white;
        border-radius: 12px;
        padding: 1.1rem 1.25rem;
        border: 1px solid var(--border);
        box-shadow: 0 1px 4px rgba(0,0,0,.05);
    }
    .kpi-label {
        font-size: .72rem;
        font-weight: 600;
        letter-spacing: .08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: .3rem;
    }
    .kpi-value {
        font-family: 'DM Serif Display', serif;
        font-size: 2.1rem;
        color: var(--navy);
        line-height: 1;
    }
    .kpi-sub {
        font-size: .75rem;
        color: var(--muted);
        margin-top: .2rem;
    }
    .kpi-green  .kpi-value { color: #22863a; }
    .kpi-amber  .kpi-value { color: #b45309; }
    .kpi-red    .kpi-value { color: #c0392b; }
    .kpi-navy   .kpi-value { color: var(--navy); }

    /* ── Section card ───────────────────────────────────────────────── */
    .section-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid var(--border);
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 4px rgba(0,0,0,.04);
    }
    .section-title {
        font-weight: 600;
        font-size: .9rem;
        color: var(--navy);
        letter-spacing: .04em;
        text-transform: uppercase;
        margin-bottom: 1rem;
        padding-bottom: .5rem;
        border-bottom: 2px solid var(--lblue);
    }

    /* ── Status badges ──────────────────────────────────────────────── */
    .badge {
        display: inline-block;
        padding: .2rem .65rem;
        border-radius: 99px;
        font-size: .72rem;
        font-weight: 600;
        letter-spacing: .04em;
    }
    .badge-green { background: #C6EFCE; color: #1a6b2a; }
    .badge-amber { background: #FFEB9C; color: #7c5c00; }
    .badge-red   { background: #FFC7CE; color: #8b0000; }

    /* ── Results table tweaks ───────────────────────────────────────── */
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    .stDataFrame thead tr th {
        background: var(--navy) !important;
        color: white !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: .8rem !important;
        font-weight: 600 !important;
    }
    .stDataFrame tbody tr td {
        font-family: 'DM Mono', monospace !important;
        font-size: .8rem !important;
    }

    /* ── Sidebar ────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: white;
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] .css-1d391kg { padding-top: 1.5rem; }

    /* ── Sidebar nav items ──────────────────────────────────────────── */
    .nav-item {
        display: flex;
        align-items: center;
        gap: .65rem;
        padding: .55rem .9rem;
        border-radius: 8px;
        margin-bottom: .2rem;
        cursor: pointer;
        font-size: .88rem;
        font-weight: 500;
        color: var(--ink);
        transition: background .15s;
    }
    .nav-item:hover, .nav-item.active {
        background: var(--lblue);
        color: var(--navy);
    }
    .nav-icon { font-size: 1.1rem; }

    /* ── Unmatched vendor chips ─────────────────────────────────────── */
    .chip-grid { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .5rem; }
    .chip {
        background: #FEE2E2;
        color: #7f1d1d;
        border-radius: 6px;
        padding: .2rem .6rem;
        font-size: .75rem;
        font-family: 'DM Mono', monospace;
        border: 1px solid #FCA5A5;
    }

    /* ── Upload zone ────────────────────────────────────────────────── */
    [data-testid="stFileUploader"] {
        border: 2px dashed var(--border) !important;
        border-radius: 10px !important;
        background: var(--bg) !important;
    }

    /* ── Button overrides ───────────────────────────────────────────── */
    .stButton > button[kind="primary"] {
        background: var(--navy);
        color: white;
        border: none;
        border-radius: 8px;
        font-family: 'DM Sans', sans-serif;
        font-weight: 600;
        letter-spacing: .04em;
        padding: .55rem 1.5rem;
        transition: background .15s, transform .1s;
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--blue);
        transform: translateY(-1px);
    }

    /* ── Slider ─────────────────────────────────────────────────────── */
    .stSlider [data-baseweb="slider"] { margin-top: .25rem; }

    /* ── Progress bar ───────────────────────────────────────────────── */
    .stProgress > div > div { background: var(--blue); }

    /* ── Tab strip ──────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] { gap: .5rem; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        font-family: 'DM Sans', sans-serif;
        font-weight: 500;
        font-size: .88rem;
    }
    .stTabs [aria-selected="true"] {
        background: white;
        color: var(--navy);
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MATCHING ENGINE  (inline — no import needed)
# ─────────────────────────────────────────────────────────────────────────────

def normalise(raw: str) -> str:
    s = raw.upper()
    s = re.sub(r'\*\S+', '', s)
    s = re.sub(r'#\S+', '', s)
    s = re.sub(r'\b(?:COM|NET|ORG|IO)\b', '', s)
    s = re.sub(r'\.(?:COM|NET|ORG|IO)', '', s)
    s = re.sub(r'\b\d{3}[-.\s]\d{3,4}[-.\s]\d{4}\b', '', s)
    s = re.sub(r'\b\d{4,}\b', '', s)
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    tokens = s.split()
    while tokens and tokens[-1] in US_STATES:
        tokens.pop()
    uk_noise = {"LON", "GREATER", "LONDON"}
    while tokens and tokens[-1] in uk_noise:
        tokens.pop()
    return ' '.join(tokens[:5]).strip().lower()


def apply_alias(norm: str, alias_map: dict) -> str | None:
    upper = norm.upper()
    for prefix, canonical in alias_map.items():
        if upper.startswith(prefix.upper()):
            return canonical
    return None


def build_supplier_index(suppliers: list[dict]) -> dict[str, dict]:
    index = {}
    for s in sorted(suppliers, key=lambda x: x["display_identifier"]):
        key = normalise(s["name"])
        if key not in index:
            index[key] = s
    return index


def run_matching(transactions, supplier_index, alias_map, auto_thresh, review_thresh):
    results = []
    for txn in transactions:
        norm    = normalise(txn["raw_merchant"])
        alias   = apply_alias(norm, alias_map)
        query   = normalise(alias) if alias else norm

        result  = process.extractOne(query, supplier_index.keys(),
                                     scorer=fuzz.token_set_ratio, score_cutoff=0)
        if result:
            matched_key, score, _ = result
            supplier = supplier_index[matched_key]
        else:
            supplier, score = None, 0

        score = int(score)
        if score >= auto_thresh:
            status = "AUTO MATCH"
        elif score >= review_thresh:
            status = "REVIEW"
        else:
            status = "NOT FOUND"

        results.append({
            **txn,
            "normalised":   norm,
            "alias_used":   alias or "",
            "matched_name": supplier["name"]               if supplier else "",
            "supplier_id":  supplier["display_identifier"] if supplier else "",
            "score":        score,
            "status":       status,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# FILE LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def load_amex_bytes(file_bytes: bytes) -> list[dict]:
    wb = xlrd.open_workbook(file_contents=file_bytes)
    sh = wb.sheets()[0]
    txns = []
    for r in range(1, sh.nrows):
        row  = sh.row_values(r)
        desc = str(row[AMEX_DESC_COL]).strip()
        if not desc:
            continue
        if any(kw in desc.upper() for kw in SKIP_KEYWORDS):
            continue
        txns.append({
            "row_num":      r + 1,
            "cardmember":   str(row[1]).strip(),
            "proc_date":    str(row[2]).strip(),
            "txn_date":     str(row[3]).strip(),
            "ref_no":       str(row[4]).strip(),
            "amount_usd":   str(row[5]).strip(),
            "raw_merchant": desc,
        })
    return txns


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def build_excel(results: list[dict], statement_name: str) -> bytes:
    wb = Workbook()
    thin  = Side(style="thin", color="BFBFBF")
    bdr   = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style(ws, r, c, val, fill=None, bold=False, align="left", font_color=None):
        cell = ws.cell(row=r, column=c, value=val)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        fc = font_color or ("FFFFFF" if bold and fill in (XLSX_COLOURS["header"], XLSX_COLOURS["subheader"]) else "000000")
        cell.font = Font(bold=bold, color=fc, size=10)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
        cell.border = bdr
        return cell

    # ── Sheet 1: Reconciliation ───────────────────────────────────────
    ws = wb.active
    ws.title = "Reconciliation"
    ws.row_dimensions[1].height = 30

    headers = ["Row#","Cardmember","Proc Date","Txn Date","Ref No",
               "Amount (USD)","Raw Amex Merchant","Normalised","Alias Used",
               "Matched Supplier","Supplier ID","Match Score","Status"]

    for c, h in enumerate(headers, 1):
        style(ws, 1, c, h, fill=XLSX_COLOURS["header"], bold=True, align="center")

    for ri, rec in enumerate(results, 2):
        st_fill = XLSX_COLOURS.get(rec["status"], "FFFFFF")
        for c, key in enumerate(
            ["row_num","cardmember","proc_date","txn_date","ref_no",
             "amount_usd","raw_merchant","normalised","alias_used",
             "matched_name","supplier_id","score"], 1):
            cell = ws.cell(row=ri, column=c, value=rec[key])
            cell.border = bdr
            cell.font = Font(size=10)
            cell.alignment = Alignment(horizontal="left", vertical="center")
        style(ws, ri, 13, rec["status"], fill=st_fill, align="center")

    for i, w in enumerate([6,14,12,12,20,14,46,32,18,36,12,12,14], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # ── Sheet 2: Summary ──────────────────────────────────────────────
    ws2 = wb.create_sheet("Summary")
    auto   = [r for r in results if r["status"] == "AUTO MATCH"]
    review = [r for r in results if r["status"] == "REVIEW"]
    nf     = [r for r in results if r["status"] == "NOT FOUND"]
    total_amt = 0.0
    for r in results:
        try:
            total_amt += float(str(r["amount_usd"]).replace(",",""))
        except (ValueError, TypeError):
            pass

    summary = [
        ("Metric", "Value", "Detail"),
        ("Statement", statement_name, ""),
        ("Run date", datetime.now().strftime("%d %b %Y %H:%M"), ""),
        ("Total transactions", len(results), ""),
        ("Total spend (USD)", f"${total_amt:,.2f}", ""),
        ("Auto-matched", len(auto), "Score ≥ 75 — ready to post"),
        ("Needs review", len(review), "Score 50–74 — confirm match"),
        ("Not found", len(nf), "Score < 50 — new vendor?"),
        ("", "", ""),
        ("UNMATCHED MERCHANTS", "", ""),
    ]
    for ri, row in enumerate(summary, 1):
        for ci, val in enumerate(row, 1):
            bold = ri == 1 or row[0] in ("UNMATCHED MERCHANTS","Metric")
            fill = XLSX_COLOURS["header"] if ri == 1 else (XLSX_COLOURS["subheader"] if row[0] == "UNMATCHED MERCHANTS" else None)
            style(ws2, ri, ci, val, fill=fill, bold=bold)
    for i, m in enumerate(sorted({r["raw_merchant"] for r in nf}), len(summary)+1):
        ws2.cell(row=i, column=1, value=m).border = bdr
        ws2.cell(row=i, column=2, value="Action required").border = bdr
    for ci, w in zip([1,2,3], [48,22,36]):
        ws2.column_dimensions[get_column_letter(ci)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "logged_in":       False,
        "username":        "",
        "results":         None,
        "suppliers":       None,
        "transactions":    None,
        "aliases":         DEFAULT_ALIASES.copy(),
        "auto_thresh":     75,
        "review_thresh":   50,
        "statement_name":  "Amex Statement",
        "active_tab":      "upload",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────────────────────

def page_login():
    st.markdown("""
    <div class="login-wrap">
        <div class="login-logo">💳 AmexRecon</div>
        <div class="login-sub">Zapro Supplier Reconciliation Portal</div>
    </div>
    """, unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns([1, 1.4, 1])
    with col_b:
        st.markdown("<div style='margin-top:-15.5rem'>", unsafe_allow_html=True)
        with st.form("login_form"):
            st.markdown("<div style='height:11rem'></div>", unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
            if submitted:
                if VALID_USERS.get(username) == password:
                    st.session_state.logged_in = True
                    st.session_state.username  = username
                    st.rerun()
                else:
                    st.error("Invalid credentials. Try admin / foxx2026")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align:center;font-size:.75rem;color:#9CA3AF;margin-top:.5rem'>"
            "Demo credentials: admin / foxx2026</p>",
            unsafe_allow_html=True
        )


def render_header():
    st.markdown(f"""
    <div class="app-header">
        <div class="app-header-title">💳 Amex → Zapro Reconciliation</div>
        <div class="app-header-user">Signed in as <strong>{st.session_state.username}</strong></div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        st.markdown("---")

        st.markdown("**Match Thresholds**")
        auto_t = st.slider("Auto-match floor", 60, 95,
                           st.session_state.auto_thresh, 5,
                           help="Score ≥ this → AUTO MATCH")
        review_t = st.slider("Review floor", 30, int(auto_t) - 5,
                              min(st.session_state.review_thresh, int(auto_t) - 5), 5,
                              help="Score between this and auto floor → REVIEW")
        st.session_state.auto_thresh   = auto_t
        st.session_state.review_thresh = review_t

        st.markdown("---")
        st.markdown("**Alias Table**")
        st.caption("Maps Amex billing codes to supplier names before matching.")

        alias_df = pd.DataFrame(st.session_state.aliases)
        edited = st.data_editor(
            alias_df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "From": st.column_config.TextColumn("Amex Code", width="small"),
                "To":   st.column_config.TextColumn("Supplier Name", width="medium"),
            },
            key="alias_editor",
        )
        st.session_state.aliases = edited.dropna(how="all").to_dict("records")

        st.markdown("---")
        if st.button("🚪 Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def page_upload():
    st.markdown("### 📂 Upload Files")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Amex Statement (.xls)</div>', unsafe_allow_html=True)
        amex_file = st.file_uploader(
            "Drop Amex XLS here", type=["xls"],
            label_visibility="collapsed", key="amex_upload"
        )
        if amex_file:
            st.session_state.statement_name = amex_file.name.replace(".xls","")
            txns = load_amex_bytes(amex_file.read())
            st.session_state.transactions = txns
            st.success(f"✅  {len(txns)} transactions loaded")
        elif st.button("Use sample file", key="use_sample_amex"):
            sample = Path("/mnt/user-data/uploads/Amex_test.xls")
            if sample.exists():
                txns = load_amex_bytes(sample.read_bytes())
                st.session_state.transactions = txns
                st.session_state.statement_name = "Statement_1008_Feb_2026"
                st.success(f"✅  {len(txns)} transactions loaded from sample")
            else:
                st.warning("Sample file not found. Please upload manually.")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Zapro Suppliers (.json)</div>', unsafe_allow_html=True)
        sup_file = st.file_uploader(
            "Drop suppliers JSON here", type=["json"],
            label_visibility="collapsed", key="sup_upload"
        )
        if sup_file:
            sup_data = json.load(sup_file)
            st.session_state.suppliers = sup_data
            active = sum(1 for s in sup_data if s.get("status") == "active")
            st.success(f"✅  {len(sup_data)} suppliers loaded ({active} active)")
        elif st.button("Use sample file", key="use_sample_sup"):
            sample = Path("/mnt/user-data/uploads/suppliers.json")
            if sample.exists():
                sup_data = json.loads(sample.read_text())
                st.session_state.suppliers = sup_data
                active = sum(1 for s in sup_data if s.get("status") == "active")
                st.success(f"✅  {len(sup_data)} suppliers loaded ({active} active) from sample")
            else:
                st.warning("Sample file not found. Please upload manually.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Run button ────────────────────────────────────────────────────
    st.markdown("---")
    ready = st.session_state.transactions and st.session_state.suppliers
    if not ready:
        st.info("Upload or load both files above to enable matching.")

    if st.button("🔍 Run Matching", type="primary",
                 disabled=not ready, use_container_width=False):
        run_and_store()


def run_and_store():
    txns      = st.session_state.transactions
    suppliers = st.session_state.suppliers

    alias_map = {row["From"]: row["To"] for row in st.session_state.aliases
                 if row.get("From") and row.get("To")}

    progress  = st.progress(0, text="Building supplier index…")
    index     = build_supplier_index([s for s in suppliers if s.get("status") == "active"])

    progress.progress(10, text=f"Matching {len(txns)} transactions…")
    results = []
    for i, txn in enumerate(txns):
        norm    = normalise(txn["raw_merchant"])
        alias   = apply_alias(norm, alias_map)
        query   = normalise(alias) if alias else norm
        result  = process.extractOne(query, index.keys(),
                                     scorer=fuzz.token_set_ratio, score_cutoff=0)
        if result:
            matched_key, score, _ = result
            supplier = index[matched_key]
        else:
            supplier, score = None, 0

        score = int(score)
        auto_t   = st.session_state.auto_thresh
        review_t = st.session_state.review_thresh
        if score >= auto_t:
            status = "AUTO MATCH"
        elif score >= review_t:
            status = "REVIEW"
        else:
            status = "NOT FOUND"

        results.append({**txn,
            "normalised":   norm,
            "alias_used":   alias or "",
            "matched_name": supplier["name"]               if supplier else "",
            "supplier_id":  supplier["display_identifier"] if supplier else "",
            "score":        score,
            "status":       status,
        })
        progress.progress(10 + int(88 * (i + 1) / len(txns)),
                          text=f"Matched {i+1}/{len(txns)}…")

    st.session_state.results = results
    progress.progress(100, text="Done!")
    st.success(f"✅  Matching complete — {len(results)} rows processed")
    st.rerun()


def page_results():
    results = st.session_state.results

    # ── KPI cards ─────────────────────────────────────────────────────
    auto   = [r for r in results if r["status"] == "AUTO MATCH"]
    review = [r for r in results if r["status"] == "REVIEW"]
    nf     = [r for r in results if r["status"] == "NOT FOUND"]
    total_amt = 0.0
    for r in results:
        try:
            total_amt += float(str(r["amount_usd"]).replace(",",""))
        except (ValueError, TypeError):
            pass

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card kpi-navy">
            <div class="kpi-label">Total Transactions</div>
            <div class="kpi-value">{len(results)}</div>
            <div class="kpi-sub">{st.session_state.statement_name}</div>
        </div>
        <div class="kpi-card kpi-navy">
            <div class="kpi-label">Total Spend</div>
            <div class="kpi-value">${total_amt:,.0f}</div>
            <div class="kpi-sub">USD</div>
        </div>
        <div class="kpi-card kpi-green">
            <div class="kpi-label">Auto Matched</div>
            <div class="kpi-value">{len(auto)}</div>
            <div class="kpi-sub">Score ≥ {st.session_state.auto_thresh} — ready to post</div>
        </div>
        <div class="kpi-card kpi-amber">
            <div class="kpi-label">Needs Review</div>
            <div class="kpi-value">{len(review)}</div>
            <div class="kpi-sub">Score {st.session_state.review_thresh}–{st.session_state.auto_thresh - 1}</div>
        </div>
        <div class="kpi-card kpi-red">
            <div class="kpi-label">Not Found</div>
            <div class="kpi-value">{len(nf)}</div>
            <div class="kpi-sub">Add to suppliers.json</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Unmatched vendor chips ─────────────────────────────────────────
    if nf:
        unmatched_names = sorted({r["raw_merchant"] for r in nf})
        chips = "".join(f'<span class="chip">{n[:40]}</span>' for n in unmatched_names)
        st.markdown(f"""
        <div class="section-card">
            <div class="section-title">❌ Vendors Not in Supplier List</div>
            <div class="chip-grid">{chips}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Results table ─────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["All Results", "Needs Review / Not Found", "Auto Matched"])

    def render_table(data):
        if not data:
            st.info("No rows in this category.")
            return
        df = pd.DataFrame(data)[
            ["row_num","txn_date","amount_usd","raw_merchant",
             "matched_name","supplier_id","score","status","alias_used"]
        ].rename(columns={
            "row_num":      "Row",
            "txn_date":     "Date",
            "amount_usd":   "Amount",
            "raw_merchant": "Amex Merchant",
            "matched_name": "Matched Supplier",
            "supplier_id":  "ID",
            "score":        "Score",
            "status":       "Status",
            "alias_used":   "Alias",
        })

        def colour_row(row):
            c = {"AUTO MATCH": "#e8f5e9", "REVIEW": "#fff8e1", "NOT FOUND": "#ffebee"}
            bg = c.get(row["Status"], "")
            return [f"background-color: {bg}"] * len(row)

        styled = df.style.apply(colour_row, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     column_config={
                         "Score": st.column_config.ProgressColumn(
                             "Score", min_value=0, max_value=100, format="%d"
                         )
                     })

    with tab1: render_table(results)
    with tab2: render_table([r for r in results if r["status"] in ("REVIEW","NOT FOUND")])
    with tab3: render_table([r for r in results if r["status"] == "AUTO MATCH"])

    # ── Download ──────────────────────────────────────────────────────
    st.markdown("---")
    xlsx_bytes = build_excel(results, st.session_state.statement_name)
    fname = f"amex_recon_{st.session_state.statement_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    st.download_button(
        label="⬇️  Download Reconciliation Excel",
        data=xlsx_bytes,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.caption(f"File: {fname}  •  {len(results)} rows  •  Reconciliation + Summary sheets")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    inject_css()
    init_state()

    if not st.session_state.logged_in:
        page_login()
        return

    render_header()
    render_sidebar()

    if st.session_state.results:
        tab_upload, tab_results = st.tabs(["📂 Upload / Run", "📊 Results"])
        with tab_upload:
            page_upload()
        with tab_results:
            page_results()
    else:
        page_upload()


if __name__ == "__main__":
    main()
