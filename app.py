from __future__ import annotations

import base64
import csv
import io
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

MONEY = Decimal("0.01")
NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")
ORDER = re.compile(r"^Order\s+(.+?)\s+-\s+Ref\s*:\s*(.+?)\s*$", re.I)
INVOICE = re.compile(r"Invoice\s+#(\d+)", re.I)
SKIP_PREFIXES = (
    "Description Your ref.", "Delivery address", "TOTAL VAT", "Subtotal", "Shipping costs",
    "Invoice ", "Total quantity", "Current balance", "Your current", "Gold still", "Please ",
    "Bank coordinates", "Any delay", "Countermark", "Produits ", "RETENTION OF TITLE", "SAS with",
    "316 769", "Code APE", "Rue du", "Tél ", "VAT:", "Folio ", "Date ", "Customer ",
    "Exonération", "Daily gold", "Comireland", "Shamrock House", "Dundrum", "D14NW93", "Irlande",
    "Siren", "payment of", "remains vested", "Retrouvez", "(Our terms", "(1)", "(2)",
)


@dataclass
class Item:
    description: str
    reference: str
    size: str
    qty: int
    metal: Decimal
    mode: str
    labour: Decimal
    supplier_unit: Decimal


def decimal_value(value: str) -> Decimal:
    return Decimal(value.replace(" ", "").replace(",", "."))


def parse_item(line: str) -> Item | None:
    tokens = line.split()
    mode_index = next((i for i in range(len(tokens) - 1, -1, -1) if tokens[i].lower() in {"a", "t", "c"}), -1)
    if mode_index < 3 or len(tokens) - mode_index not in {3, 4}:
        return None
    after = tokens[mode_index + 1:]
    if not all(NUMBER.match(value) for value in after):
        return None
    try:
        metal = decimal_value(tokens[mode_index - 1])
        qty = int(tokens[mode_index - 2])
    except (InvalidOperation, ValueError):
        return None
    ref_index = mode_index - 3
    size = ""
    if (ref_index >= 1 and NUMBER.match(tokens[ref_index])
            and any(char.isdigit() for char in tokens[ref_index - 1])):
        size = tokens[ref_index]
        ref_index -= 1
    if ref_index < 0:
        return None
    reference = tokens[ref_index]
    if not any(char.isdigit() for char in reference):
        return None
    description = " ".join(tokens[:ref_index]).strip()
    labour = decimal_value(after[0])
    supplier_unit = decimal_value(after[-2] if len(after) == 3 else after[0])
    return Item(description, reference, size, qty, metal, tokens[mode_index].lower(), labour, supplier_unit)


def extract_invoice(pdf_stream) -> tuple[str, OrderedDict[str, list[Item]]]:
    reader = PdfReader(pdf_stream)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    invoice_match = INVOICE.search(text)
    if not invoice_match:
        raise ValueError("The PDF does not contain a recognizable invoice number.")
    groups: OrderedDict[str, list[Item]] = OrderedDict()
    current_ref: str | None = None
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        order_match = ORDER.match(line)
        if order_match:
            current_ref = order_match.group(2).strip().split()[0]
            groups.setdefault(current_ref, [])
            continue
        if not current_ref or not line or line.startswith(SKIP_PREFIXES):
            continue
        item = parse_item(line)
        if item:
            groups[current_ref].append(item)
    groups = OrderedDict((ref, items) for ref, items in groups.items() if items)
    if not groups:
        raise ValueError("No product rows grouped by Order Ref were found in this PDF.")
    return invoice_match.group(1), groups


def item_price(item: Item, gold_fix: Decimal, markup: Decimal) -> Decimal:
    description = item.description.upper()
    if "18CT" in description or "18K" in description:
        value = gold_fix * item.metal * Decimal("2") / item.qty + item.labour * Decimal("1.27")
    elif "9CT" in description or "9K" in description:
        value = gold_fix * item.metal / item.qty + item.labour * Decimal("1.27")
    else:
        value = item.supplier_unit * (Decimal("1") + markup / Decimal("100"))
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def euro(value: Decimal) -> str:
    return f"€ {value:.2f}"


def csv_for_order(invoice: str, order_ref: str, items: list[Item], gold_fix: Decimal, markup: Decimal) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([f"Date {date.today():%d/%m/%Y}", "Gold Fix", euro(gold_fix), "", "", "", "", "", ""])
    writer.writerow([f"Invoice #{invoice}", "", "", "", "", "", "", "", ""])
    writer.writerow(["Issued by ComIreland Ltd", "", "", "", "", "", "", "", ""])
    writer.writerow([f"Order Ref : {order_ref}", "", "", "", "", "", "", "", ""])
    writer.writerow([])
    writer.writerow(["Description", "Reference", "Size", "Qty", "Metal", "Mode", "Unit", "Total"])
    priced = [(item, item_price(item, gold_fix, markup)) for item in items]
    grand_total = sum((unit * item.qty for item, unit in priced), Decimal("0")).quantize(MONEY)
    writer.writerow(["", "", "", "", "", "", "", euro(grand_total)])
    for item, unit in priced:
        writer.writerow([
            item.description, item.reference, item.size, item.qty,
            f"{item.metal:.2f}".replace(".", ","), item.mode, euro(unit), euro(unit * item.qty),
        ])
    return "\ufeff".encode("utf-8") + output.getvalue().encode("utf-8")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "order"


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/process")
def process_invoice():
    uploaded = request.files.get("invoice")
    if not uploaded or not uploaded.filename.lower().endswith(".pdf"):
        return jsonify(error="Choose a PDF invoice."), 400
    try:
        gold_fix = decimal_value(request.form.get("gold_fix", ""))
        markup = decimal_value(request.form.get("markup", "35"))
        if gold_fix <= 0 or markup < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return jsonify(error="Enter a valid positive gold fix and a non-negative markup."), 400
    try:
        invoice, groups = extract_invoice(uploaded.stream)
        files = []
        for order_ref, items in groups.items():
            content = csv_for_order(invoice, order_ref, items, gold_fix, markup)
            files.append({
                "order_ref": order_ref,
                "filename": f"invoice_{invoice}_{safe_name(order_ref)}.csv",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "item_count": len(items),
            })
        return jsonify(invoice=invoice, files=files)
    except (ValueError, InvalidOperation) as exc:
        return jsonify(error=str(exc)), 422
    except Exception:
        app.logger.exception("Invoice processing failed")
        return jsonify(error="The invoice could not be processed. Confirm it uses the supported company format."), 422


@app.get("/api/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=os.getenv("FLASK_DEBUG") == "1")
