# Amex → Zapro Supplier Reconciliation

Browser-based tool that matches American Express credit card statement transactions against a Zapro supplier list using fuzzy string matching, with optional invoice and purchase order enrichment.

## Features

### V1 (`app.py`)
- Login with role-based access (admin / finance)
- Upload Amex `.xls` statement and Zapro suppliers `.json`
- Configurable fuzzy match thresholds
- Colour-coded results table with KPI summary cards
- Editable alias table for resolving Amex billing codes
- One-click Excel export (Reconciliation + Summary sheets)

### V2 (`app_v2.py`) — primary version
All V1 features, plus:
- **Live API integration** — fetch suppliers, invoices, and purchase orders directly from Zapro via the `ZaproClient`
- **Config persistence** — API credentials stored in `config.json`, loaded on startup
- **Admin-only API configuration** — Base URL and API key fields visible only to the `admin` user
- **Invoice and PO enrichment** — cross-references each matched transaction against Zapro invoices by exact amount, then near-amount (within 2% or $0.50), then by supplier
- **Supplier grouping** — amount matching works across related supplier IDs (e.g., Amazon and Amazon Business Partner share a group)
- **Client/Project extraction** — cascades through invoice billing segments, PO ship-to title, PO custom fields, and PO bill-to title
- **Alternative match suggestions** — REVIEW rows include up to two alternative supplier candidates
- Three-sheet Excel export (Reconciliation + Summary + Invoice Detail)

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API credentials (V2 only, admin users)

On first run, log in as `admin`, open the sidebar, and enter the Zapro Base URL and API Key. Click **Save API Config**. Credentials are written to `config.json` in the project directory.

Alternatively, create `config.json` manually before starting:

```json
{
  "zapro_base_url": "https://your-tenant.zapro.ai",
  "zapro_api_key": "your-api-key-here"
}
```

### 3. Run the app

```bash
# V2 (recommended)
streamlit run app_v2.py

# V1 (basic, no API integration)
streamlit run app.py
```

The app opens at `http://localhost:8501`. Log in with one of the credentials listed under [Credentials](#credentials).

## Architecture

Both versions are single-file Streamlit applications. All logic is inline — no shared modules between `app.py` and `app_v2.py`. V2 imports `ZaproClient` and `ZaproAPIError` from `fetch_zapro_data.py`.

### Data flow

```
Login
  └── Upload / Fetch
        ├── Amex XLS  ──► load_amex_bytes()  ──► transactions list
        └── Zapro data
              ├── Via API: ZaproClient.fetch_*()
              └── Via file upload: JSON file uploaders
                    ├── suppliers.json
                    ├── invoices.json    (enrichment, optional)
                    └── purchase_orders.json  (enrichment, optional)

Run Matching
  └── build_supplier_index()
        └── run_matching() / run_and_store()
              ├── normalise()  ──  strips noise from merchant strings
              ├── apply_alias()  ──  resolves billing codes before fuzzy search
              └── rapidfuzz.process.extract()  ──  token_set_ratio scoring
                    └── enrich_transaction()  (V2 only, if invoices + POs loaded)
                          ├── Exact amount match (same supplier or related group)
                          ├── Exact amount match (any supplier)
                          └── Near-amount match within supplier/group (±2% or $0.50)

Results
  └── page_results()
        ├── KPI cards (supplier matching + enrichment rows)
        ├── Tabbed results table
        └── build_excel()  ──  formatted .xlsx download
```

### Key functions

| Function | File | Purpose |
|---|---|---|
| `normalise(raw)` | both | Strips domains, phone numbers, state codes, and special characters from Amex merchant strings; returns lowercase, max 5 tokens |
| `apply_alias(norm, alias_map)` | both | Prefix-matches the normalised string against the alias table; returns the canonical supplier name if found |
| `build_supplier_index(suppliers)` | both | Creates `{normalised_name: supplier_dict}` from the active suppliers list |
| `run_matching(...)` | both | Orchestrates per-transaction normalise → alias → fuzzy match pipeline |
| `run_and_store()` | both | Streamlit entry point for matching; drives the progress bar and stores results in session state |
| `build_excel(results, name)` | both | Generates the downloadable `.xlsx` workbook |
| `enrich_transaction(...)` | V2 | Looks up invoice and PO records for a matched supplier by amount |
| `_build_enrichment(inv, po_index, match_type)` | V2 | Extracts invoice/PO fields and calls `_get_project()` |
| `_get_project(inv, po_rec)` | V2 | Cascades through billing segments, PO ship-to title, PO custom fields, and PO bill-to title to find the client/project name |
| `build_invoice_indexes(invoices)` | V2 | Builds `{amount: [invoices]}` and `{supplier_id: [invoices]}` dicts |
| `build_po_index(pos)` | V2 | Builds `{display_identifier: po_record}` lookup |
| `load_config()` / `save_config(...)` | V2 | Read/write `config.json` for API credentials |
| `ZaproClient.generate_token()` | fetch_zapro_data.py | POSTs to `/api/external/tokens/generate` and caches the bearer token |
| `ZaproClient.fetch_all(endpoint)` | fetch_zapro_data.py | Paginates through any Zapro API endpoint (1000 records per page) |
| `ZaproClient.fetch_suppliers()` | fetch_zapro_data.py | Fetches `/api/external/suppliers.json` |
| `ZaproClient.fetch_invoices()` | fetch_zapro_data.py | Fetches `/api/external/invoices.json` |
| `ZaproClient.fetch_purchase_orders()` | fetch_zapro_data.py | Fetches `/api/external/purchase_orders.json` |

## Configuration

### `config.json`

Stores API credentials for V2. This file is gitignored and should not be committed.

```json
{
  "zapro_base_url": "https://your-tenant.zapro.ai",
  "zapro_api_key": "your-api-key-here"
}
```

`load_config()` merges this file with `DEFAULT_CONFIG` on startup. If the file is missing or malformed, defaults are used (`zapro_base_url` defaults to `https://versatex.zapro.ai`, `zapro_api_key` defaults to empty string).

### Environment variables (standalone fetch script only)

`fetch_zapro_data.py` can be run as a standalone script to export data to JSON and CSV files. It reads credentials from environment variables:

| Variable | Default | Description |
|---|---|---|
| `ZAPRO_BASE_URL` | `https://versatex.zapro.ai` | Zapro tenant base URL |
| `ZAPRO_API_KEY` | _(required)_ | API key — script exits if not set |

```bash
export ZAPRO_BASE_URL=https://your-tenant.zapro.ai
export ZAPRO_API_KEY=your-api-key
python fetch_zapro_data.py
```

Output is written to a timestamped directory: `YYYYMMDD_HHMMSS/` containing `suppliers.json`, `invoices.json`, `purchase_orders.json`, and flattened CSV versions of each.

## Credentials

Credentials are hardcoded in `VALID_USERS`:

| Username | Password | Role |
|---|---|---|
| `admin` | `foxx2026` | Full access including API configuration |
| `finance` | `recon123` | Reconciliation access; cannot modify API credentials |

## File Structure

```
Stream/
├── app.py                  # V1 — basic reconciliation
├── app_v2.py               # V2 — with API integration and enrichment
├── fetch_zapro_data.py     # ZaproClient class + standalone export script
├── requirements.txt        # Python dependencies
├── config.json             # API credentials (gitignored, created at runtime)
└── .gitignore
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | >=1.32.0 | Web application framework |
| `xlrd` | >=2.0.1 | Reading Amex `.xls` statements |
| `rapidfuzz` | >=3.6.0 | Fuzzy string matching |
| `openpyxl` | >=3.1.2 | Writing formatted Excel output |
| `pandas` | >=2.0.0 | DataFrame manipulation and display |
| `requests` | _(transitive)_ | HTTP calls in `ZaproClient` |
