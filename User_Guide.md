# User Guide — Amex → Zapro Reconciliation

This guide covers daily use of the reconciliation tool for both admin and finance users.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Logging In](#logging-in)
3. [Admin: Setting Up API Credentials](#admin-setting-up-api-credentials)
4. [Loading Data](#loading-data)
   - [Fetching from the Zapro API](#fetching-from-the-zapro-api)
   - [Uploading Files Manually](#uploading-files-manually)
5. [Uploading the Amex Statement](#uploading-the-amex-statement)
6. [Running the Reconciliation](#running-the-reconciliation)
7. [Understanding Results](#understanding-results)
   - [KPI Cards](#kpi-cards)
   - [Match Statuses](#match-statuses)
   - [Results Table](#results-table)
   - [Enrichment Columns](#enrichment-columns)
   - [Invoice Detail Tab](#invoice-detail-tab)
8. [Downloading the Excel Report](#downloading-the-excel-report)
9. [Configuring Match Thresholds](#configuring-match-thresholds)
10. [Managing the Alias Table](#managing-the-alias-table)
11. [Troubleshooting](#troubleshooting)

---

## Getting Started

Open the app URL in your browser. The app runs entirely in the browser — no installation is needed on your machine.

The tool has two user roles:

| Role | Username | Can configure API | Can run reconciliation |
|---|---|---|---|
| Admin | `admin` | Yes | Yes |
| Finance | `finance` | No | Yes |

---

## Logging In

The login screen shows a username and password form. Enter your credentials and click **Sign In**.

If the credentials are incorrect, an error message appears below the form. The app does not lock accounts after failed attempts.

Once logged in, your username appears in the top-right corner of the header bar. To sign out, click **Sign Out** at the bottom of the sidebar.

---

## Admin: Setting Up API Credentials

The app can fetch suppliers, invoices, and purchase orders directly from Zapro. This requires a Base URL and API Key, which only the admin user can configure.

**To set credentials:**

1. Log in as `admin`.
2. Open the sidebar (it is open by default).
3. Scroll down to the **Zapro API Configuration** section.
4. Enter the **Base URL** — for example, `https://your-tenant.zapro.ai`.
5. Enter the **API Key** in the password field.
6. Click **Save API Config**.

The credentials are saved to `config.json` in the application directory and will be loaded automatically on every subsequent startup.

**Finance users** see either "Zapro API configured" (when credentials are set) or a note to contact admin (when they are not).

---

## Loading Data

The app needs two things to run a reconciliation:

- An Amex statement file (`.xls`)
- Zapro supplier data

Invoice and purchase order data are optional but required for invoice matching and client/project enrichment.

### Fetching from the Zapro API

When API credentials are configured, the Upload page shows a **Zapro Data** section with a **Fetch from Zapro** button. Clicking it fetches all three datasets — suppliers, invoices, and purchase orders — in one operation.

A progress panel appears while the data is loading:

```
Fetching data from Zapro API...
  Generating auth token...
  Fetching suppliers...
    142 suppliers (138 active)
  Fetching invoices...
    1,024 invoices
  Fetching purchase orders...
    387 purchase orders
Zapro data loaded
```

Once complete, a confirmation message shows the record counts. The data remains in memory for the session; you do not need to re-fetch unless you want fresher data.

### Uploading Files Manually

If API credentials are not configured, or if you want to use exported JSON files instead, the manual upload panels are shown directly. When API credentials are configured, manual upload panels are accessible inside an expandable section labelled "Or upload JSON files manually".

**Suppliers JSON** — required for matching. This is the direct export from Zapro containing supplier records with `name`, `display_identifier`, and `status` fields.

**Invoices JSON** — optional; required for invoice matching and enrichment columns.

**Purchase Orders JSON** — optional; required to populate PO amounts, Procore PO IDs, and client/project names.

Each uploader accepts `.json` files. After a successful upload, a confirmation message shows the number of records loaded.

---

## Uploading the Amex Statement

The Amex Statement uploader accepts `.xls` files (not `.xlsx`). Drop the file onto the uploader or click to browse.

After parsing, the app shows the number of transactions found. Rows containing the words REMITTANCE, PAYMENT, or BALANCE in the merchant description are automatically excluded.

The file name (without the `.xls` extension) is used as the statement name in KPI cards and the Excel export filename.

---

## Running the Reconciliation

Once the Amex statement and supplier data are both loaded, the **Run Matching** button becomes active. Click it to start.

A progress bar tracks the operation. For each transaction, the app:

1. Normalises the raw merchant string (strips noise, limits to 5 tokens, lowercases)
2. Checks the alias table for a prefix match
3. Runs a fuzzy match against all active suppliers using token set ratio scoring
4. If invoices and purchase orders are loaded, attempts to find a matching invoice by amount

When complete, the Results tab opens automatically.

If you change thresholds or the alias table after running, a warning banner appears at the top of the Results page. Click **Run Matching** again to recalculate.

---

## Understanding Results

### KPI Cards

The top of the Results page displays summary cards:

| Card | Description |
|---|---|
| Total Transactions | Number of rows processed from the Amex file |
| Total Spend | Sum of all transaction amounts in USD |
| Auto Matched | Transactions matched with high confidence |
| Needs Review | Transactions matched at lower confidence |
| Not Found | Transactions with no supplier match |

When invoice and PO data were loaded, a second row of cards appears:

| Card | Description |
|---|---|
| Invoices Matched | Transactions for which an invoice was found |
| No Invoice Found | Transactions with no matching invoice |
| Client Projects | Count of distinct client/project values found across matched invoices |

### Match Statuses

Each transaction receives one of three statuses based on the fuzzy match score (0–100):

| Status | Score Range | Meaning |
|---|---|---|
| AUTO MATCH | Score >= auto threshold (default 75) | High-confidence match; ready to post |
| REVIEW | Between review floor (default 50) and auto threshold | Likely correct but should be confirmed |
| NOT FOUND | Below review floor | Supplier not in the list; may be a new vendor |

Scores are calculated using rapidfuzz `token_set_ratio`, which handles word-order differences and partial strings well.

### Results Table

The table has three tabs:

- **All Results** — every transaction
- **Needs Review / Not Found** — only REVIEW and NOT FOUND rows
- **Auto Matched** — only AUTO MATCH rows

Each row is colour-coded:
- Light green — AUTO MATCH
- Light amber — REVIEW
- Light red — NOT FOUND

The **Score** column shows a progress bar from 0 to 100. The **Alternatives** column (REVIEW rows only) shows up to two other supplier candidates and their scores, formatted as `Supplier Name (score) | Other Name (score)`.

Unmatched merchants are also displayed as chips above the results table for a quick overview.

### Enrichment Columns

When invoice and PO data were loaded, the following columns are appended to each row:

| Column | Description |
|---|---|
| Invoice # | Invoice number from Zapro |
| Inv Date | Invoice date (YYYY-MM-DD) |
| Inv Status | Invoice status as reported by Zapro |
| Invoice Total | Invoice net total, formatted as `$1,234.56` |
| PO # | Purchase order number linked to the invoice |
| PO Total | PO net total, formatted as `$1,234.56` |
| Procore PO ID | Value of the "Procore PO ID" custom field on the invoice |
| Client / Project | Project name extracted from invoice billing segments, PO ship-to title, PO custom fields, or PO bill-to title |
| Inv Match | How the invoice was matched (see table below) |

**Invoice match types:**

| Value | Meaning |
|---|---|
| EXACT | One invoice at the same amount for the matched supplier or a related supplier in the same group |
| EXACT (N inv) | Multiple invoices at the same amount for the supplier/group |
| EXACT (amt only) | Exactly one invoice at this amount across all suppliers, but for a different supplier |
| AMBIGUOUS (N inv) | Multiple invoices at the same amount across different suppliers |
| NEAR MATCH | Invoice within 2% or $0.50 of the transaction amount for the supplier/group |
| NOT MATCHED | No invoice found |
| NO AMOUNT | The transaction amount could not be parsed |

Enrichment cells are greyed out in the table and Excel export for rows where no invoice was found.

### Invoice Detail Tab

When invoice data is loaded, a fourth tab — **Invoice Detail** — appears. It shows only the rows where an invoice was matched, making it easier to review enrichment results in isolation.

---

## Downloading the Excel Report

Click **Download Reconciliation Excel** below the results table to download the report. The file is named:

```
amex_recon_<statement_name>_<YYYYMMDD_HHMM>.xlsx
```

The workbook contains:

**Sheet 1 — Reconciliation**

All transactions with every column visible in the results table. Core matching columns have a dark navy header; enrichment columns have a soft green header. The Status cell is colour-coded by match result. Matched invoice amounts are highlighted in green. Rows with no invoice match have greyed-out enrichment cells.

**Sheet 2 — Summary**

Overview statistics: transaction counts, total spend, auto/review/not-found counts, and invoice enrichment counts. Followed by a list of all unmatched merchant strings.

**Sheet 3 — Invoice Detail**

Present only when at least one invoice was matched. Contains the same rows as the Invoice Detail tab. EXACT match rows have a light green background; NEAR MATCH rows have a light yellow background.

---

## Configuring Match Thresholds

The sidebar contains two sliders under **Match Thresholds**:

**Auto-match floor** (range 60–95, default 75)
A score at or above this value produces an AUTO MATCH result. Raising this threshold reduces false positives but increases REVIEW volume. Lowering it accepts more matches automatically.

**Review floor** (range 30 to auto floor minus 5, default 50)
Scores between this value and the auto floor produce a REVIEW result. Scores below this produce NOT FOUND. The review floor cannot exceed (auto floor - 5).

Changes take effect on the next **Run Matching** click. If you change thresholds after viewing results, a warning banner reminds you to re-run.

---

## Managing the Alias Table

The alias table maps Amex billing codes to supplier names before fuzzy matching runs. This is useful for merchants that appear on statements with codes or truncated names that do not resemble their Zapro supplier name.

The table is editable directly in the sidebar. Each row has two fields:

| Field | Description |
|---|---|
| Amex Code | The prefix to look for in the normalised merchant string (case-insensitive) |
| Supplier Name | The canonical name to use for fuzzy matching instead |

**Example:** The alias `AMZN → Amazon` means any merchant starting with `AMZN` (after normalisation) will be matched as if it were `Amazon`.

To add a row, click the `+` icon at the bottom of the table. To remove a row, select it and press the delete key. Changes apply on the next **Run Matching** click.

Aliases use prefix matching, not substring or exact matching. The alias `HOME DEPOT` matches `HOME DEPOT STORE 1234` but not `THE HOME DEPOT`.

---

## Troubleshooting

**"Zapro API error: HTTP 401"**
The API key is incorrect or has expired. Admin should update the key in the sidebar and save again.

**"Zapro API error: HTTP 429"**
The API rate limit was reached. The client will retry up to 3 times with backoff. If the error persists, wait a few minutes and try again.

**"Failed to parse Amex file"**
The file may not be in the expected format. The tool reads `.xls` files (legacy Excel) using column positions: cardmember in column 2, process date column 3, transaction date column 4, reference number column 5, amount column 6, merchant description column 7 (zero-indexed column 6). The file must have a header row.

**"Sample file not found"**
Sample files are expected at `/mnt/user-data/uploads/`. These are only available in the hosted environment. Upload your own files instead.

**Transactions show NOT FOUND but the supplier exists**
Check the alias table — the Amex merchant string may need an alias entry. Also check that the supplier's `status` field is `"active"` in the Zapro data; inactive suppliers are excluded from matching.

**Invoice amounts are not matching despite the supplier matching correctly**
The invoice lookup uses the `invoice_net_total` field and the transaction `amount_usd` field. If the Amex amount includes tax or shipping that Zapro records as separate line items, the net total will differ. The near-match tolerance is 2% or $0.50, whichever is larger. For suppliers that invoice across multiple entity IDs, check that both supplier IDs appear in the same `SUPPLIER_GROUPS` entry.

**Results look stale after changing thresholds**
The warning banner "Settings changed since last run" confirms this. Click **Run Matching** to recalculate.

**Client/Project column is empty for matched invoices**
The app checks four sources in order: invoice line item billing segment named `Project-Foxx`, PO `ship_to_info.title`, PO custom fields with "project" or "client" in the field name, and PO `bill_to_info.title`. If all four are empty or missing, the column will be blank for that row.
