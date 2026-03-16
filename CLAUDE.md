# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Amex → Zapro Supplier Reconciliation tool built with Streamlit. Matches Amex credit card statement transactions against a Zapro supplier list using fuzzy string matching (rapidfuzz). Two versions exist:

- **`app.py`** — V1: basic reconciliation (upload Amex XLS + suppliers JSON, run matching, download Excel)
- **`app_v2.py`** — V2 (primary): adds live Zapro API integration, config persistence, invoice/PO enrichment, supplier grouping, amount matching, and a 3-sheet Excel export

`fetch_zapro_data.py` contains the `ZaproClient` class imported by V2, and doubles as a standalone export script.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run V1
streamlit run app.py

# Run V2 (primary version)
streamlit run app_v2.py

# Run standalone Zapro data export (writes JSON + CSV to timestamped directory)
export ZAPRO_BASE_URL=https://your-tenant.zapro.ai
export ZAPRO_API_KEY=your-api-key
python fetch_zapro_data.py
```

No tests, no linter, no build step.

## Architecture

Both app files are single-file Streamlit apps. Everything is inline — no shared code between `app.py` and `app_v2.py`. V2 imports from `fetch_zapro_data.py`.

### Flow

1. **Login** → hardcoded credentials in `VALID_USERS` dict (`admin`/`foxx2026`, `finance`/`recon123`)
2. **Load data** → Amex `.xls` (parsed via `xlrd`) + Zapro data (via API fetch or JSON file uploads)
3. **Matching** → `normalise()` cleans merchant names → `apply_alias()` resolves known billing codes → `rapidfuzz.process.extract` with `token_set_ratio` scorer finds best supplier match
4. **Enrichment** (V2, when invoices + POs loaded) → `enrich_transaction()` cross-references each matched transaction against invoice data by amount
5. **Results** → colour-coded Streamlit dataframe + KPI cards
6. **Export** → `build_excel()` generates formatted `.xlsx` via openpyxl

### Key Functions

| Function | File | Purpose |
|---|---|---|
| `normalise(raw)` | both | Strips `*suffix`, `#suffix`, TLDs, phone numbers, 4+ digit numbers, non-alphanumeric chars, trailing US state codes, and UK location noise; returns lowercase, max 5 tokens |
| `apply_alias(norm, alias_map)` | both | Prefix-matches (case-insensitive `startswith`) against user-editable alias table; returns canonical supplier name or `None` |
| `build_supplier_index(suppliers)` | both | Filters to `status == "active"` suppliers; creates `{normalised_name: supplier_dict}` keyed by `display_identifier` sort order |
| `run_matching(txns, index, aliases, auto_t, review_t)` | both | Per-transaction normalise → alias → fuzzy match; V2 version uses `process.extract(limit=3)` and populates `alt_matches` |
| `run_and_store()` | both | Streamlit orchestration: builds indexes, loops transactions with progress bar, calls `enrich_transaction()` in V2, stores in `st.session_state.results` |
| `build_excel(results, name)` | both | Writes `.xlsx` to `BytesIO`; V2 version adds enrichment columns to sheet 1 and a third "Invoice Detail" sheet |
| `enrich_transaction(vid, amt, inv_by_amount, inv_by_vid, po_index)` | V2 | Three-pass lookup: exact amount + same supplier, exact amount any supplier, near-amount within supplier group (±2% or $0.50) |
| `_build_enrichment(inv, po_index, match_type)` | V2 | Extracts invoice/PO fields; calls `_get_project()` |
| `_get_project(inv, po_rec)` | V2 | Cascade: invoice billing segment `Project-Foxx` → PO `ship_to_info.title` → PO custom fields containing "project"/"client" → PO `bill_to_info.title` |
| `build_invoice_indexes(invoices)` | V2 | Returns `(by_amount, by_vid)` — amount-keyed and supplier-ID-keyed dicts |
| `build_po_index(pos)` | V2 | `{display_identifier: po_record}` lookup |
| `load_config()` / `save_config(url, key)` | V2 | Read/write `config.json` for API credentials |
| `_fetch_zapro_data()` | V2 | Streamlit wrapper: instantiates `ZaproClient`, calls all three fetch methods with `st.status` progress display |
| `inject_css()` | both | Injects all custom styles as a single `st.markdown(..., unsafe_allow_html=True)` call |

### ZaproClient (fetch_zapro_data.py)

```python
client = ZaproClient(base_url, api_key)
client.generate_token()        # POSTs to /api/external/tokens/generate; caches token
client.fetch_suppliers()       # GET /api/external/suppliers.json (paginated)
client.fetch_invoices()        # GET /api/external/invoices.json (paginated)
client.fetch_purchase_orders() # GET /api/external/purchase_orders.json (paginated)
client.fetch_all(endpoint)     # Generic paginated fetcher used by the above three
```

`_request_with_retry()` handles up to 3 attempts with exponential backoff (2^attempt seconds) on status codes `{429, 500, 502, 503, 504}`. Pagination reads `body["pagination"]["total_pages"]` and `body["pagination"]["current_page"]`; page size is 1000.

`ZaproAPIError` is a plain `Exception` subclass with an optional `status_code` attribute.

## V2 Additions

### API Integration and Config Persistence

- `CONFIG_PATH = Path(__file__).parent / "config.json"` — credentials file location
- `DEFAULT_CONFIG = {"zapro_base_url": "https://versatex.zapro.ai", "zapro_api_key": ""}` — fallback values
- `load_config()` merges `config.json` with `DEFAULT_CONFIG`; silently falls back on `JSONDecodeError` or `OSError`
- `save_config(url, key)` overwrites `config.json` completely
- `init_state()` calls `load_config()` to populate `zapro_base_url` and `zapro_api_key` in `st.session_state`

### Admin-Only API Configuration (sidebar)

- `render_sidebar()` checks `st.session_state.username == "admin"` to show or hide the API config fields
- Admin sees: Base URL text input, API Key password input, "Save API Config" button
- Non-admin sees: "Zapro API configured" success message if key is set, otherwise a note to contact admin

### Fetch from Zapro Button

- Shown on `page_upload()` when `st.session_state.zapro_api_key` is truthy
- Calls `_fetch_zapro_data()` which uses `st.status(...)` for live progress feedback
- On success, sets `st.session_state.suppliers`, `st.session_state.invoices`, `st.session_state.purchase_orders`
- File uploaders remain available inside a "Or upload JSON files manually" expander

### Supplier Grouping

```python
SUPPLIER_GROUPS = [
    {"V1018", "V1024"},   # Amazon + Amazon Business Partner
    {"V1013", "V1002"},   # Menards duplicates
    {"V1008", "V1100"},   # H Hafner & Sons variants
]
```

`_suppliers_related(vid_a, vid_b)` returns `True` if both IDs appear in the same group. Exact-amount and near-amount matching both expand the candidate set across group members.

### Enrichment Match Types

| `inv_match_type` | Meaning |
|---|---|
| `EXACT` | One invoice at exact amount for the matched supplier or its group |
| `EXACT (N inv)` | Multiple invoices at exact amount for the supplier/group |
| `EXACT (amt only)` | Exactly one invoice at this amount but for a different supplier |
| `AMBIGUOUS (N inv)` | Multiple invoices at this amount across different suppliers |
| `NEAR MATCH` | Invoice within 2% or $0.50 of the transaction amount for the supplier/group |
| `NOT MATCHED` | No invoice found |
| `NO AMOUNT` | Transaction amount could not be parsed |

### Debug Sections (temporary)

Both are admin-only and wrapped in `st.expander`:
- **PO Custom Fields** — shown on `page_upload()` when POs are loaded; displays top-level and line-item custom fields for the first three POs
- **Enrichment State** — shown in the sidebar during `run_and_store()`; prints index sizes, sample invoice keys, and sample PO keys

### Excel Export Changes (V2)

Sheet 1 "Reconciliation" adds enrichment columns (Invoice #, Invoice Date, Invoice Status, Invoice Net Total, PO Number, PO Net Total, Procore PO ID, Client/Project, Inv Match Type) with a distinct soft-green header background. Enrichment cells grey out when no invoice was found for that row. The Invoice Net Total cell turns green when an invoice is matched.

Sheet 3 "Invoice Detail" is written only when at least one invoice match exists. It contains a filtered view of matched rows with EXACT matches highlighted light green and NEAR MATCH rows highlighted light yellow.

### Alternative Matches (V2)

`run_matching()` calls `process.extract(..., limit=3)` instead of `extractOne`. REVIEW rows include an `alt_matches` field containing up to two alternative candidates formatted as `"Supplier Name (score) | Other Name (score)"`.

## Key Data Structures

### Transaction dict

```python
{
    "row_num": int,
    "cardmember": str,
    "proc_date": str,
    "txn_date": str,
    "ref_no": str,
    "amount_usd": str,      # string, not float — parsed at match time
    "raw_merchant": str,
}
```

### Result dict (after matching)

Core fields (both versions):
```python
{
    **txn,                  # all transaction fields above
    "normalised": str,      # output of normalise(raw_merchant)
    "alias_used": str,      # canonical alias name, or ""
    "matched_name": str,    # supplier["name"] or ""
    "supplier_id": str,     # supplier["display_identifier"] or ""
    "score": int,           # 0–100
    "status": str,          # "AUTO MATCH" | "REVIEW" | "NOT FOUND"
}
```

V2 additional fields:
```python
{
    "alt_matches": str,         # "" or "Name1 (score) | Name2 (score)"
    "inv_match_type": str,      # see Enrichment Match Types table above
    "invoice_number": str,
    "invoice_status": str,
    "invoice_net_total": str,   # formatted "$1,234.56" or ""
    "invoice_date": str,        # "YYYY-MM-DD" or ""
    "po_number": str,
    "po_net_total": str,        # formatted "$1,234.56" or ""
    "procore_po_id": str,       # from invoice custom field "Procore PO ID"
    "client_project": str,      # from _get_project() cascade
}
```

### Session State Keys

| Key | Type | Description |
|---|---|---|
| `logged_in` | bool | Authentication state |
| `username` | str | `"admin"` or `"finance"` |
| `results` | list[dict] or None | Matching output |
| `suppliers` | list[dict] or None | Raw Zapro supplier records |
| `transactions` | list[dict] or None | Parsed Amex rows |
| `invoices` | list[dict] or None | Raw Zapro invoice records (V2) |
| `purchase_orders` | list[dict] or None | Raw Zapro PO records (V2) |
| `aliases` | list[dict] | `[{"From": str, "To": str}, ...]` |
| `auto_thresh` | int | Auto-match score floor (default 75) |
| `review_thresh` | int | Review score floor (default 50) |
| `statement_name` | str | Derived from uploaded filename |
| `active_tab` | str | `"upload"` or `"results"` |
| `last_run_config` | str or None | MD5 hash of aliases + thresholds at last run (V2) |
| `zapro_base_url` | str | Loaded from config.json on startup (V2) |
| `zapro_api_key` | str | Loaded from config.json on startup (V2) |

## Conventions

- All CSS is injected inline via `inject_css()` — a single `st.markdown()` with `unsafe_allow_html=True`
- Amex XLS column positions are hardcoded (`AMEX_DESC_COL = 6` is the merchant description column)
- The normalisation pipeline strips US state abbreviations (`US_STATES` set) and UK location noise (`{"LON", "GREATER", "LONDON"}`) from the tail of merchant strings
- Alias matching is prefix-based (case-insensitive `startswith`)
- `st.set_page_config()` must remain the first Streamlit call in both app files
- `SKIP_KEYWORDS = {"REMITTANCE", "PAYMENT", "BALANCE"}` — rows containing these strings are excluded from the transaction list during Amex XLS parsing
- Amount parsing strips commas before converting to float: `float(str(amount).replace(",", ""))`
- `config.json` is gitignored and must not be committed

## Config File Format

`config.json` is written by `save_config()` and read by `load_config()`:

```json
{
  "zapro_base_url": "https://your-tenant.zapro.ai",
  "zapro_api_key": "your-api-key-here"
}
```

Missing keys are filled from `DEFAULT_CONFIG`. The file is created the first time an admin saves credentials through the sidebar.
