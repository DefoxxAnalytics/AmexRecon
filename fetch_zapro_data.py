import json
import csv
import os
import sys
import time
from datetime import datetime

import requests

PER_PAGE = 1000
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ZaproAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class ZaproClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._token = None

    def _request_with_retry(self, method, url, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.request(method, url, **kwargs)
                if resp.status_code == 200:
                    return resp
                if resp.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                    raise ZaproAPIError(
                        f"HTTP {resp.status_code} from {url}: {resp.text[:500]}",
                        status_code=resp.status_code,
                    )
                wait = RETRY_BACKOFF ** attempt
                time.sleep(wait)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == MAX_RETRIES:
                    raise ZaproAPIError(f"Request failed after {MAX_RETRIES} attempts: {exc}") from exc
                wait = RETRY_BACKOFF ** attempt
                time.sleep(wait)
        raise ZaproAPIError(f"Request failed after {MAX_RETRIES} attempts") from last_exc

    def generate_token(self):
        url = f"{self.base_url}/api/external/tokens/generate"
        resp = self._request_with_retry(
            "POST", url,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json", "Accept": "application/json"},
            json={},
        )
        body = resp.json()
        if body.get("status") != "success":
            raise ZaproAPIError(f"Token generation failed: {body}")
        self._token = body["token"]
        return self._token

    def fetch_all(self, endpoint):
        if not self._token:
            self.generate_token()
        all_records = []
        page = 1
        prev_page = 0
        headers = {"Authorization": f"Bearer {self._token}", "x-api-key": self.api_key}
        while True:
            resp = self._request_with_retry(
                "GET", f"{self.base_url}{endpoint}",
                headers=headers,
                params={"per_page": PER_PAGE, "page": page},
            )
            body = resp.json()
            if body.get("status") != "success":
                raise ZaproAPIError(f"API error on {endpoint} page {page}: {body}")
            records = body.get("data", [])
            pagination = body.get("pagination", {})
            all_records.extend(records)
            total_pages = pagination.get("total_pages", 1)
            current_page = pagination.get("current_page", page)
            if current_page >= total_pages:
                break
            if current_page <= prev_page:
                break
            prev_page = current_page
            page += 1
        return all_records

    def fetch_suppliers(self):
        return self.fetch_all("/api/external/suppliers.json")

    def fetch_invoices(self):
        return self.fetch_all("/api/external/invoices.json")

    def fetch_purchase_orders(self):
        return self.fetch_all("/api/external/purchase_orders.json")


def save_json(data, filename, output_dir):
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {path}")


INVOICE_DATE_FIELDS = {
    "invoice_date", "last_modified_date", "last_modified_time",
    "invoice_filled_date", "payment_due_date", "invoice_paid_date",
}

SUPPLIER_DATE_FIELDS = {
    "creation_date", "activation_date", "last_modified_time",
}

PO_DATE_FIELDS = {
    "issued_at", "created_at", "submitted_at", "last_modified_time",
}


def nullify_empty_dates(record, date_fields):
    for field in date_fields:
        if field in record and isinstance(record[field], str) and not record[field].strip():
            record[field] = None


def clean_empty_dates(invoices, suppliers, purchase_orders):
    for inv in invoices:
        nullify_empty_dates(inv, INVOICE_DATE_FIELDS)
    for sup in suppliers:
        nullify_empty_dates(sup, SUPPLIER_DATE_FIELDS)
    for po in purchase_orders:
        nullify_empty_dates(po, PO_DATE_FIELDS)


def flatten_po_rows(purchase_orders):
    rows = []
    for po in purchase_orders:
        base = {
            "po_id": po.get("po_id"),
            "display_identifier": po.get("display_identifier"),
            "status": po.get("status"),
            "receipt_status": po.get("receipt_status"),
            "invoice_status": po.get("invoice_status"),
            "shipment_status": po.get("shipment_status"),
            "confirmation_status": po.get("confirmation_status"),
            "issued_at": po.get("issued_at"),
            "created_at": po.get("created_at"),
            "submitted_at": po.get("submitted_at"),
            "last_modified_time": po.get("last_modified_time"),
            "po_net_total": po.get("po_net_total"),
            "po_gross_total": po.get("po_gross_total"),
            "po_tax_total": po.get("po_tax_total"),
            "po_shipping_total": po.get("po_shipping_total"),
            "currency_code": po.get("currency_code"),
        }

        requestor = po.get("requestor") or {}
        base["requestor_id"] = requestor.get("id")
        base["requestor_name"] = requestor.get("name")
        base["requestor_email"] = requestor.get("email")

        supplier = po.get("supplier") or {}
        base["supplier_id"] = supplier.get("id")
        base["supplier_name"] = supplier.get("name")
        base["supplier_code"] = supplier.get("display_identifier")

        ship_to = po.get("ship_to_info") or {}
        base["ship_to_title"] = ship_to.get("title")
        base["ship_to_location_code"] = ship_to.get("location_code")
        ship_address = ship_to.get("address") or {}
        base["ship_to_address1"] = ship_address.get("address1")
        base["ship_to_address2"] = ship_address.get("address2")
        base["ship_to_city"] = ship_address.get("city")
        base["ship_to_state"] = ship_address.get("state")
        base["ship_to_zipcode"] = ship_address.get("zipcode")
        base["ship_to_country"] = ship_address.get("country")

        bill_to = po.get("bill_to_info") or {}
        base["bill_to_title"] = bill_to.get("title")
        base["bill_to_location_code"] = bill_to.get("location_code")
        bill_address = bill_to.get("address") or {}
        base["bill_to_name"] = bill_address.get("name")
        base["bill_to_address1"] = bill_address.get("address1")
        base["bill_to_address2"] = bill_address.get("address2")
        base["bill_to_city"] = bill_address.get("city")
        base["bill_to_state"] = bill_address.get("state")
        base["bill_to_zipcode"] = bill_address.get("zipcode")
        base["bill_to_country"] = bill_address.get("country")

        for cf in po.get("custom_fields") or []:
            key = cf.get("field_name", "").lower().replace(" ", "_").replace("(", "").replace(")", "")
            if key:
                base[f"po_cf_{key}"] = cf.get("value")

        line_items = po.get("line_items") or []
        if not line_items:
            rows.append(base)
            continue

        for li in line_items:
            li_base = {**base}
            li_base["line_item_id"] = li.get("line_item_id")
            li_base["line_number"] = li.get("line_number")
            li_base["item"] = li.get("item")
            li_base["item_type"] = li.get("item_type")
            li_base["quantity"] = li.get("quantity")
            li_base["price"] = li.get("price")
            li_base["discount"] = li.get("discount")
            li_base["total_price"] = li.get("total_price")
            li_base["need_by_date"] = li.get("need_by_date")
            li_base["line_currency_code"] = li.get("currency_code")
            li_base["unspsc_commodity_code"] = li.get("unspsc_commodity_code")
            li_base["category"] = li.get("category")
            li_base["supplier_part_id"] = li.get("supplier_part_id")

            for cf in li.get("custom_fields") or []:
                key = cf.get("field_name", "").lower().replace(" ", "_")
                if key:
                    li_base[f"li_cf_{key}"] = cf.get("value")

            mappings = li.get("invoice_line_mappings") or []
            if not mappings:
                rows.append(li_base)
                continue

            for mapping in mappings:
                row = {**li_base}
                row["matched_quantity"] = mapping.get("matched_quantity")
                row["matched_price"] = mapping.get("matched_price")
                row["approved"] = mapping.get("approved")
                row["pending_approval"] = mapping.get("pending_approval")
                row["uninvoiced"] = mapping.get("uninvoiced")

                inv_line = mapping.get("invoice_line") or {}
                row["inv_line_id"] = inv_line.get("invoice_line_id")
                row["inv_line_quantity"] = inv_line.get("quantity")
                row["inv_line_price"] = inv_line.get("price")
                row["inv_line_total_price"] = inv_line.get("total_price")

                invoice = inv_line.get("invoice") or {}
                row["mapped_invoice_id"] = invoice.get("invoice_id")
                row["mapped_invoice_number"] = invoice.get("display_identifier")
                row["mapped_invoice_ext_number"] = invoice.get("number")
                row["mapped_invoice_status"] = invoice.get("status")

                rows.append(row)
    return rows


def flatten_invoice_rows(invoices):
    rows = []
    for inv in invoices:
        base = {
            "invoice_id": inv.get("invoice_id"),
            "invoice_number": inv.get("number"),
            "status": inv.get("status"),
            "invoice_date": inv.get("invoice_date"),
            "invoice_net_total": inv.get("invoice_net_total"),
            "invoice_gross_total": inv.get("invoice_gross_total"),
            "invoice_tax_total": inv.get("invoice_tax_total"),
            "invoice_shipping_total": inv.get("invoice_shipping_total"),
            "last_modified_date": inv.get("last_modified_date"),
            "invoice_filled_date": inv.get("invoice_filled_date"),
            "payment_due_date": inv.get("payment_due_date"),
            "invoice_paid_date": inv.get("invoice_paid_date"),
            "external_reference": inv.get("external_reference"),
            "payment_terms": inv.get("payment_terms"),
            "payment_terms_days": inv.get("payment_terms_days"),
        }
        po = inv.get("po_details") or {}
        base["po_id"] = po.get("po_id")
        base["po_number"] = po.get("display_identifier")

        supplier = inv.get("supplier") or {}
        base["supplier_id"] = supplier.get("id")
        base["supplier_name"] = supplier.get("name")
        base["supplier_code"] = supplier.get("display_identifier")

        for cf in inv.get("custom_fields") or []:
            key = cf.get("field_name", "").lower().replace(" ", "_")
            if key:
                base[f"inv_cf_{key}"] = cf.get("value")

        line_items = inv.get("line_items") or []
        if not line_items:
            rows.append(base)
            continue

        for li in line_items:
            row = {**base}
            row["line_item_id"] = li.get("line_item_id")
            row["line_number"] = li.get("line_number")
            row["item"] = li.get("item")
            row["quantity"] = li.get("quantity")
            row["price"] = li.get("price")
            row["total_price"] = li.get("total_price")
            row["currency_code"] = li.get("currency_code")
            row["uom"] = li.get("uom")
            row["commodity_code"] = li.get("commodity_code")
            row["commodity_name"] = li.get("commodity_name")

            for seg in li.get("billing_segments") or []:
                seg_key = seg.get("segment_name", "").lower().replace(" ", "_")
                if seg_key:
                    row[seg_key] = seg.get("segment_value")

            for cf in li.get("custom_fields") or []:
                key = cf.get("field_name", "").lower().replace(" ", "_")
                if key:
                    row[f"li_cf_{key}"] = cf.get("value")

            rows.append(row)
    return rows


def flatten_supplier_rows(suppliers):
    rows = []
    for sup in suppliers:
        row = {
            "id": sup.get("id"),
            "display_identifier": sup.get("display_identifier"),
            "name": sup.get("name"),
            "status": sup.get("status"),
            "creation_date": sup.get("creation_date"),
            "activation_date": sup.get("activation_date"),
            "payment_term_name": sup.get("payment_term_name"),
            "shipping_term_code": sup.get("shipping_term_code"),
            "shipping_method_name": sup.get("shipping_method_name"),
            "external_reference": sup.get("external_reference"),
            "invoice_email_address": ";".join(sup.get("invoice_email_address") or []),
            "default_po_email": ";".join(sup.get("default_po_email") or []),
        }

        contact = sup.get("contact") or {}
        row["contact_first_name"] = contact.get("first_name")
        row["contact_last_name"] = contact.get("last_name")
        row["contact_phone"] = contact.get("phone")
        row["contact_email"] = contact.get("email")

        address = sup.get("address") or {}
        row["address_name"] = address.get("name")
        row["address_line1"] = address.get("line1")
        row["address_line2"] = address.get("line2")
        row["address_city"] = address.get("city")
        row["address_state"] = address.get("state")
        row["address_zipcode"] = address.get("zipcode")
        row["address_country"] = address.get("country")

        sites = sup.get("supplier_sites") or []
        for i, site in enumerate(sites):
            prefix = f"site_{i + 1}_"
            for site_key, site_val in site.items():
                if isinstance(site_val, dict):
                    for nested_k, nested_v in site_val.items():
                        row[f"{prefix}{site_key}_{nested_k}"] = nested_v
                else:
                    row[f"{prefix}{site_key}"] = site_val

        for cf in sup.get("custom_fields") or []:
            key = cf.get("field_name", "").lower().replace(" ", "_")
            if key:
                row[f"cf_{key}"] = cf.get("value")

        rows.append(row)
    return rows


def save_csv(rows, filename, output_dir):
    if not rows:
        print(f"No data to save for {filename}")
        return
    all_keys = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    path = os.path.join(output_dir, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {path} ({len(rows)} rows)")


def main():
    base_url = os.environ.get("ZAPRO_BASE_URL", "https://versatex.zapro.ai")
    api_key = os.environ.get("ZAPRO_API_KEY", "")
    if not api_key:
        sys.exit("Error: ZAPRO_API_KEY environment variable is not set")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, datetime.now().strftime("%Y%m%d_%H%M%S"))

    print(f"=== Zapro Data Export ({base_url}) ===\n")

    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}\n")

    client = ZaproClient(base_url, api_key)

    try:
        print("Generating token...")
        client.generate_token()

        print("\nFetching invoices...")
        invoices = client.fetch_invoices()
        print(f"Total invoices: {len(invoices)}")

        print("\nFetching suppliers...")
        suppliers = client.fetch_suppliers()
        print(f"Total suppliers: {len(suppliers)}")

        print("\nFetching purchase orders...")
        purchase_orders = client.fetch_purchase_orders()
        print(f"Total purchase orders: {len(purchase_orders)}")
    except ZaproAPIError as exc:
        print(f"\nAPI Error: {exc}")
        sys.exit(1)

    print("\nCleaning empty date fields...")
    clean_empty_dates(invoices, suppliers, purchase_orders)

    print("\nSaving JSON files...")
    save_json(invoices, "invoices.json", output_dir)
    save_json(suppliers, "suppliers.json", output_dir)
    save_json(purchase_orders, "purchase_orders.json", output_dir)

    print("\nSaving CSV files...")
    invoice_rows = flatten_invoice_rows(invoices)
    save_csv(invoice_rows, "invoices.csv", output_dir)

    supplier_rows = flatten_supplier_rows(suppliers)
    save_csv(supplier_rows, "suppliers.csv", output_dir)

    po_rows = flatten_po_rows(purchase_orders)
    save_csv(po_rows, "purchase_orders.csv", output_dir)

    print("\n=== Done ===")
    print(f"Invoices: {len(invoices)} records -> {len(invoice_rows)} CSV rows (expanded by line items)")
    print(f"Suppliers: {len(suppliers)} records -> {len(supplier_rows)} CSV rows")
    print(f"POs: {len(purchase_orders)} records -> {len(po_rows)} CSV rows (expanded by line items + invoice mappings)")


if __name__ == "__main__":
    main()
