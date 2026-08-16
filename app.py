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
from xml.sax.saxutils import escape

from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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


@dataclass
class OrderGroup:
    reference: str
    label: str
    items: list[Item]


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
    if (ref_index >= 1 and "," in tokens[ref_index] and NUMBER.match(tokens[ref_index])
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


def extract_invoice(pdf_stream) -> tuple[str, OrderedDict[str, OrderGroup]]:
    reader = PdfReader(pdf_stream)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    invoice_match = INVOICE.search(text)
    if not invoice_match:
        raise ValueError("The PDF does not contain a recognizable invoice number.")
    groups: OrderedDict[str, OrderGroup] = OrderedDict()
    current_ref: str | None = None
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        order_match = ORDER.match(line)
        if order_match:
            current_ref = order_match.group(2).strip().split()[0]
            groups.setdefault(current_ref, OrderGroup(current_ref, line, []))
            continue
        if (current_ref and line.lower().startswith("countermark")
                and groups[current_ref].items):
            groups[current_ref].items[-1].description += f"\n{line}"
            continue
        if not current_ref or not line or line.startswith(SKIP_PREFIXES):
            continue
        item = parse_item(line)
        if item:
            groups[current_ref].items.append(item)
    groups = OrderedDict((ref, group) for ref, group in groups.items() if group.items)
    if not groups:
        raise ValueError("No product rows grouped by Order Ref were found in this PDF.")
    return invoice_match.group(1), groups


def item_price(item: Item, gold_fix: Decimal, markup: Decimal, gold_markup: Decimal) -> Decimal:
    description = item.description.upper()
    is_18ct = "18CT" in description or "18K" in description
    is_9ct = "9CT" in description or "9K" in description
    if is_18ct or is_9ct:
        value = item.supplier_unit * (Decimal("1") + gold_markup / Decimal("100"))
        if item.mode.lower() == "t":
            gold_multiplier = Decimal("2") if is_18ct else Decimal("1")
            value += gold_fix * item.metal * gold_multiplier / item.qty
    else:
        value = item.supplier_unit * (Decimal("1") + markup / Decimal("100"))
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def euro(value: Decimal) -> str:
    return f"€ {value:.2f}"


def csv_rows_for_order(invoice: str, group: OrderGroup, gold_fix: Decimal, markup: Decimal, gold_markup: Decimal) -> list[list]:
    priced = [(item, item_price(item, gold_fix, markup, gold_markup)) for item in group.items]
    grand_total = sum((unit * item.qty for item, unit in priced), Decimal("0")).quantize(MONEY)
    rows = [
        [],
        [f"Date {date.today():%d/%m/%Y}", "Gold Fix", euro(gold_fix), "", "", "", "", "", ""],
        [f"Invoice #{invoice}", "", "", "", "", "", "", "", ""],
        [group.label, "", "", "", "", "", "", "", ""],
        [],
        ["Description", "Reference", "Size", "Qty", "Metal", "Mode", "Unit", "Total"],
        ["", "", "", "", "", "", "", euro(grand_total)],
        [],
    ]
    for item, unit in priced:
        rows.append([
            item.description, item.reference, item.size, item.qty,
            f"{item.metal:.2f}".replace(".", ","), item.mode, euro(unit), euro(unit * item.qty),
        ])
    return rows


def csv_for_order(invoice: str, group: OrderGroup, gold_fix: Decimal, markup: Decimal, gold_markup: Decimal) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows(csv_rows_for_order(invoice, group, gold_fix, markup, gold_markup))
    return "\ufeff".encode("utf-8") + output.getvalue().encode("utf-8")


def pdf_for_order(invoice: str, group: OrderGroup, gold_fix: Decimal, markup: Decimal, gold_markup: Decimal) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("InvoiceBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10)
    small = ParagraphStyle("InvoiceSmall", parent=body, fontSize=7, leading=9)
    header = ParagraphStyle("InvoiceHeader", parent=small, textColor=colors.white, fontName="Helvetica-Bold")
    right = ParagraphStyle("InvoiceRight", parent=body, alignment=TA_RIGHT)

    def paragraph(value, style=body):
        text = escape(str(value)).replace("\n", "<br/>").replace("€", "&euro;")
        return Paragraph(text or "&#160;", style)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#657386"))
        canvas.drawString(15 * mm, 9 * mm, f"Invoice #{invoice} · {group.label}")
        canvas.drawRightString(282 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=15 * mm, title=f"Invoice {invoice} - {group.reference}",
    )
    story = [
        Paragraph(f"Invoice #{escape(invoice)}", styles["Title"]),
        Spacer(1, 3 * mm),
        paragraph(f"Date {date.today():%d/%m/%Y}    ·    Gold Fix € {gold_fix:.2f}    ·    Gold Markup {gold_markup:.2f}%"),
        Spacer(1, 2 * mm),
        Paragraph(escape(group.label), styles["Heading2"]),
        Spacer(1, 4 * mm),
    ]
    table_rows = [[paragraph(value, header) for value in
                   ["Description", "Reference", "Size", "Qty", "Metal", "Mode", "Unit", "Total"]]]
    order_total = Decimal("0")
    for item in group.items:
        unit = item_price(item, gold_fix, markup, gold_markup)
        total = (unit * item.qty).quantize(MONEY)
        order_total += total
        table_rows.append([
            paragraph(item.description), paragraph(item.reference), paragraph(item.size, right),
            paragraph(item.qty, right), paragraph(f"{item.metal:.2f}", right), paragraph(item.mode),
            paragraph(euro(unit), right), paragraph(euro(total), right),
        ])
    table_rows.append([paragraph("Order total", right), "", "", "", "", "", "",
                       paragraph(euro(order_total), right)])
    table = Table(table_rows, colWidths=[91 * mm, 26 * mm, 14 * mm, 14 * mm, 18 * mm, 15 * mm, 25 * mm, 27 * mm],
                  repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12233B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -2), 0.35, colors.HexColor("#DCE3EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EDF4FF")),
        ("SPAN", (0, -1), (6, -1)),
        ("BOX", (0, -1), (-1, -1), 0.5, colors.HexColor("#9FB0C4")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


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
        gold_markup = decimal_value(request.form.get("gold_markup", "27"))
        if gold_fix <= 0 or markup < 0 or gold_markup < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return jsonify(error="Enter a valid positive gold fix and non-negative markup values."), 400
    try:
        invoice, groups = extract_invoice(uploaded.stream)
        files = []
        for order_ref, group in groups.items():
            content = csv_for_order(invoice, group, gold_fix, markup, gold_markup)
            pdf_content = pdf_for_order(invoice, group, gold_fix, markup, gold_markup)
            files.append({
                "order_ref": group.label,
                "filename": f"invoice_{invoice}_{safe_name(order_ref)}.csv",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "pdf_filename": f"invoice_{invoice}_{safe_name(order_ref)}.pdf",
                "pdf_base64": base64.b64encode(pdf_content).decode("ascii"),
                "item_count": len(group.items),
                "preview_rows": csv_rows_for_order(invoice, group, gold_fix, markup, gold_markup),
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
