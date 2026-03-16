# Amex → Zapro Supplier Reconciliation

Browser-based tool that matches American Express credit card statement transactions against a Zapro supplier list using fuzzy string matching, with invoice and purchase order enrichment.

## Features

- **Live API integration** — fetch suppliers, invoices, and purchase orders directly from Zapro
- **Config persistence** — API credentials and user accounts stored in `config.json` (gitignored)
- **Hashed authentication** — SHA-256 hashed passwords with admin user management
- **Auto-detect Amex format** — parses both simplified and full Amex export layouts by matching header names
- **Invoice and PO enrichment** — cross-references matched transactions against invoices by exact amount, near-amount (within 2% or $0.50), and by supplier group
- **Supplier grouping** — amount matching works across related supplier IDs (e.g., Amazon and Amazon Business Partner)
- **Client/Project extraction** — cascades through invoice billing segments, PO ship-to title, PO custom fields, and PO bill-to title
- **Alternative match suggestions** — REVIEW rows include up to two alternative supplier candidates
- **In-app How-To guide** — dedicated tab with alias table docs, match status reference, and usage instructions
- **Three-sheet Excel export** — Reconciliation + Summary + Invoice Detail

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

### 3. Configure API credentials (admin only)

Log in as `admin`, open the sidebar, enter the Zapro Base URL and API Key, and click **Save API Config**. Credentials are written to `config.json` and available to all users.

Alternatively, create `config.json` manually:

```json
{
  "zapro_base_url": "https://your-tenant.zapro.ai",
  "zapro_api_key": "your-api-key-here",
  "users": {}
}
```

## Architecture

Single-file Streamlit application (`app.py`). Imports `ZaproClient` and `ZaproAPIError` from `fetch_zapro_data.py` for API access.

### Data flow

```
Login (SHA-256 hashed passwords from config.json)
  └── Upload / Fetch
        ├── Amex XLS  ──► load_amex_bytes()  ──► transactions list
        └── Zapro data
              ├── Via API: ZaproClient.fetch_*()
              └── Via file upload: JSON file uploaders (fallback)

Run Matching
  └── build_supplier_index()
        └── run_and_store()
              ├── normalise()  ──  strips noise from merchant strings
              ├── apply_alias()  ──  resolves billing codes before fuzzy search
              └── rapidfuzz.process.extract()  ──  token_set_ratio scoring
                    └── enrich_transaction()  (if invoices + POs loaded)

Results
  └── page_results()
        ├── KPI cards with percentage badges
        ├── Tabbed results table
        └── build_excel()  ──  formatted .xlsx download
```

### Key functions

| Function | File | Purpose |
|---|---|---|
| `load_amex_bytes(file_bytes)` | app.py | Auto-detects Amex XLS columns by header names; uses supplemental cardmember when available |
| `normalise(raw)` | app.py | Strips domains, phone numbers, state codes, special characters; returns lowercase, max 5 tokens |
| `apply_alias(norm, alias_map)` | app.py | Prefix-matches against the alias table; returns canonical supplier name |
| `build_supplier_index(suppliers)` | app.py | Creates `{normalised_name: supplier_dict}` from active suppliers |
| `enrich_transaction(...)` | app.py | Three-pass invoice lookup: exact amount + same supplier, exact amount any supplier, near-amount within group |
| `_get_project(inv, po_rec)` | app.py | Cascades through billing segments, PO ship-to, PO custom fields, PO bill-to |
| `verify_login(username, password)` | app.py | Checks SHA-256 hash against `config.json` users |
| `ZaproClient` | fetch_zapro_data.py | API client with token generation, paginated fetching, retry with backoff |

## Configuration

### `config.json`

Stores API credentials and user accounts. Gitignored — never committed.

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

On first run, default users are seeded (`admin`/`foxx2026`, `finance`/`recon123`). Admin can add, reset, or remove users via the sidebar.

### Environment variables (standalone fetch script)

`fetch_zapro_data.py` can run standalone to export data to JSON and CSV:

```bash
export ZAPRO_BASE_URL=https://your-tenant.zapro.ai
export ZAPRO_API_KEY=your-api-key
python fetch_zapro_data.py
```

## Authentication

Passwords are SHA-256 hashed. Default credentials on first run:

| Username | Password | Role |
|---|---|---|
| `admin` | `foxx2026` | Full access: API config, user management, reconciliation |
| `finance` | `recon123` | Reconciliation only; cannot modify API credentials or users |

Admin can manage users via the sidebar (add, reset password, remove). The admin account cannot be removed.

## File Structure

```
Stream/
├── app.py                  # Main Streamlit application
├── fetch_zapro_data.py     # ZaproClient class + standalone export script
├── requirements.txt        # Python dependencies
├── config.json             # API credentials + users (gitignored, created at runtime)
├── README.md
├── CLAUDE.md
├── User_Guide.md
└── .gitignore
```

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web application framework |
| `xlrd` | Reading Amex `.xls` statements |
| `rapidfuzz` | Fuzzy string matching |
| `openpyxl` | Writing formatted Excel output |
| `pandas` | DataFrame manipulation and display |
| `requests` | HTTP calls in `ZaproClient` |
