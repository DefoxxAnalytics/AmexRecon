# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Amex → Zapro Supplier Reconciliation tool built with Streamlit. Matches Amex credit card statement transactions against a Zapro supplier list using fuzzy string matching (rapidfuzz).

- **`app.py`** — main Streamlit app with live Zapro API integration, config persistence, hashed auth, invoice/PO enrichment, supplier grouping, in-app How-To guide, and 3-sheet Excel export
- **`fetch_zapro_data.py`** — `ZaproClient` class imported by the app, also works as a standalone export script

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py

# Run standalone Zapro data export (writes JSON + CSV to timestamped directory)
export ZAPRO_BASE_URL=https://your-tenant.zapro.ai
export ZAPRO_API_KEY=your-api-key
python fetch_zapro_data.py
```

No tests, no linter, no build step.

## Architecture

Single-file Streamlit app (`app.py`). Imports `ZaproClient` and `ZaproAPIError` from `fetch_zapro_data.py`.

### Flow

1. **Login** → SHA-256 hashed credentials stored in `config.json`; verified by `verify_login()`
2. **Load data** → Amex `.xls` (auto-detected column layout via `_find_col()`) + Zapro data (via API fetch or JSON file uploads)
3. **Matching** → `normalise()` cleans merchant names → `apply_alias()` resolves known billing codes → `rapidfuzz.process.extract` with `token_set_ratio` scorer finds best supplier match
4. **Enrichment** (when invoices + POs loaded) → `enrich_transaction()` cross-references each matched transaction against invoice data by amount
5. **Results** → colour-coded Streamlit dataframe + KPI cards with percentage badges
6. **Export** → `build_excel()` generates formatted `.xlsx` via openpyxl

### Key Functions

| Function | Purpose |
|---|---|
| `_find_col(headers, *candidates)` | Auto-detects Amex XLS column by matching header name substrings |
| `load_amex_bytes(file_bytes)` | Parses Amex XLS; uses supplemental cardmember when available, falls back to basic |
| `normalise(raw)` | Strips `*suffix`, `#suffix`, TLDs, phone numbers, 4+ digit numbers, non-alphanumeric chars, trailing US state codes, and UK location noise; returns lowercase, max 5 tokens |
| `apply_alias(norm, alias_map)` | Prefix-matches (case-insensitive `startswith`) against user-editable alias table; returns canonical supplier name or `None` |
| `build_supplier_index(suppliers)` | Filters to `status == "active"` suppliers; creates `{normalised_name: supplier_dict}` keyed by `display_identifier` sort order |
| `run_and_store()` | Streamlit orchestration: builds indexes, loops transactions with progress bar, calls `enrich_transaction()`, stores in `st.session_state.results` |
| `enrich_transaction(vid, amt, inv_by_amount, inv_by_vid, po_index)` | Three-pass lookup: exact amount + same supplier, exact amount any supplier, near-amount within supplier group (±2% or $0.50) |
| `_get_project(inv, po_rec)` | Cascade: invoice billing segment `Project-Foxx` → PO `ship_to_info.title` → PO custom fields containing "project"/"client" → PO `bill_to_info.title` |
| `verify_login(username, password)` | Hashes input with SHA-256 and compares against `config.json` users |
| `_hash_pw(password)` | Returns `hashlib.sha256(password.encode()).hexdigest()` |
| `load_config()` / `save_config(config)` | Read/write `config.json` for API credentials and user accounts |
| `_fetch_zapro_data()` | Streamlit wrapper: instantiates `ZaproClient`, calls all three fetch methods with `st.status` progress display |
| `page_howto()` | In-app How-To guide: quick start, API setup, match statuses, enrichment columns, alias table, Excel report |
| `inject_css()` | Injects all custom styles (Inter font, Clean & Modern theme) as a single `st.markdown(..., unsafe_allow_html=True)` call |

### ZaproClient (fetch_zapro_data.py)

```python
client = ZaproClient(base_url, api_key)
client.generate_token()        # POSTs to /api/external/tokens/generate; caches token
client.fetch_suppliers()       # GET /api/external/suppliers.json (paginated)
client.fetch_invoices()        # GET /api/external/invoices.json (paginated)
client.fetch_purchase_orders() # GET /api/external/purchase_orders.json (paginated)
client.fetch_all(endpoint)     # Generic paginated fetcher used by the above three
```

`_request_with_retry()` handles up to 3 attempts with exponential backoff on status codes `{429, 500, 502, 503, 504}`. Page size is 1000.

## Authentication

- `ADMIN_ROLE = "admin"` — constant used for role checks
- `DEFAULT_USERS` — seeded on first run with SHA-256 hashed passwords
- `verify_login()` hashes input and compares against `config.json` users dict
- Admin sidebar: add/reset users, remove non-admin users
- Admin account cannot be removed

## Config File Format

`config.json` stores API credentials and user accounts (gitignored):

```json
{
  "zapro_base_url": "https://your-tenant.zapro.ai",
  "zapro_api_key": "your-api-key-here",
  "users": {
    "admin": "<sha256-hash>",
    "finance": "<sha256-hash>"
  }
}
```

`load_config()` merges with `DEFAULT_CONFIG` on read. Missing keys are filled from defaults.

## Enrichment Match Types

| `inv_match_type` | Meaning |
|---|---|
| `EXACT` | One invoice at exact amount for the matched supplier or its group |
| `EXACT (N inv)` | Multiple invoices at exact amount for the supplier/group |
| `EXACT (amt only)` | Exactly one invoice at this amount but for a different supplier |
| `AMBIGUOUS (N inv)` | Multiple invoices at this amount across different suppliers |
| `NEAR MATCH` | Invoice within 2% or $0.50 of the transaction amount for the supplier/group |
| `NOT MATCHED` | No invoice found |
| `NO AMOUNT` | Transaction amount could not be parsed |

## Conventions

- All CSS is injected inline via `inject_css()` — Inter font family, Clean & Modern theme
- Amex XLS columns are auto-detected by header names via `_find_col()`; falls back to hardcoded positions
- Supplemental Cardmember (actual card user) is preferred over Basic Cardmember (account holder)
- The normalisation pipeline strips US state abbreviations (`US_STATES` set) and UK location noise from merchant strings
- Alias matching is prefix-based (case-insensitive `startswith`)
- `st.set_page_config()` must remain the first Streamlit call
- `SKIP_KEYWORDS = {"REMITTANCE", "PAYMENT", "BALANCE"}` — rows containing these are excluded during parsing
- `config.json` is gitignored and must not be committed
