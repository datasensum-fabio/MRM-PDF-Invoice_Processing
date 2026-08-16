import io
import base64
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import app as application


PDF_TEXT = """Invoice #4690899
Order WEB - Ref : WEB235520.0182
Hoops earrings pair plain 9K YG 650068.3 1 1,20 t 8,78 9,36 9,36
Countermark :Dorothy
Earrings pair w. cult.FWpearl gold plated Brass 135047 1 1,95 a 41,98 41,98 41,98
Order WEB - Ref : WEB235522.0205 note for warehouse
Set of 5 925 silver extension chain RALLAG.5 1 2,00 a 15,30 15,30 15,30
Coll. oz.vert+blc ag925rh 332544.4 1 2,50 a 22,25 22,25 22,25
"""


def parsed_fixture():
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: PDF_TEXT)])
    with patch.object(application, "PdfReader", return_value=reader):
        return application.extract_invoice(io.BytesIO(b"pdf"))


def test_health():
    application.app.config["TESTING"] = True
    response = application.app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"ok": True}


def test_parser_groups_sample_order_and_keeps_all_products():
    invoice, groups = parsed_fixture()
    assert invoice == "4690899"
    assert groups["WEB235520.0182"].label == "Order WEB - Ref : WEB235520.0182"
    assert len(groups["WEB235520.0182"].items) == 2
    assert {item.reference for item in groups["WEB235520.0182"].items} == {"650068.3", "135047"}
    assert groups["WEB235520.0182"].items[0].description.endswith("\nCountermark :Dorothy")
    assert "WEB235522.0205" in groups
    numeric_reference = groups["WEB235522.0205"].items[1]
    assert numeric_reference.reference == "332544.4"
    assert numeric_reference.description == "Coll. oz.vert+blc ag925rh"


def test_pricing_formulas():
    nine = application.Item("Ring 9CT YG", "A1", "", 2, Decimal("1.20"), "t", Decimal("8"), Decimal("10"))
    eighteen = application.Item("Ring 18CT YG", "A2", "", 2, Decimal("1.20"), "t", Decimal("8"), Decimal("10"))
    gold_without_metal = application.Item("Ring 9K YG", "A4", "", 2, Decimal("1.20"), "a", Decimal("8"), Decimal("10"))
    other = application.Item("Silver ring", "A3", "", 1, Decimal("1"), "a", Decimal("10"), Decimal("10"))
    assert application.item_price(nine, Decimal("65.20"), Decimal("35"), Decimal("27")) == Decimal("51.82")
    assert application.item_price(eighteen, Decimal("65.20"), Decimal("35"), Decimal("27")) == Decimal("90.94")
    assert application.item_price(gold_without_metal, Decimal("65.20"), Decimal("35"), Decimal("27")) == Decimal("12.70")
    assert application.item_price(other, Decimal("65.20"), Decimal("35"), Decimal("27")) == Decimal("13.50")


def test_process_returns_one_csv_per_order_ref():
    application.app.config["TESTING"] = True
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: PDF_TEXT)])
    with patch.object(application, "PdfReader", return_value=reader):
        response = application.app.test_client().post("/api/process", data={
            "invoice": (io.BytesIO(b"pdf"), "4690899.pdf"),
            "gold_fix": "65.20",
            "markup": "35",
            "gold_markup": "27",
        })
    assert response.status_code == 200
    assert response.json["invoice"] == "4690899"
    assert len(response.json["files"]) == 2
    selected = next(file for file in response.json["files"] if file["order_ref"] == "Order WEB - Ref : WEB235520.0182")
    assert selected["filename"] == "invoice_4690899_WEB235520.0182.csv"
    assert selected["item_count"] == 2
    sample = base64.b64decode(selected["content_base64"]).decode("utf-8-sig")
    pdf = base64.b64decode(selected["pdf_base64"])
    assert selected["pdf_filename"] == "invoice_4690899_WEB235520.0182.pdf"
    assert pdf.startswith(b"%PDF-")
    assert sample.startswith("\r\n")
    assert "Issued by ComIreland Ltd" not in sample
    assert "Order WEB - Ref : WEB235520.0182" in sample
    assert selected["preview_rows"][0] == []
    assert selected["preview_rows"][7] == []
    assert selected["preview_rows"][8][0] == "Hoops earrings pair plain 9K YG\nCountermark :Dorothy"
    assert "Countermark :Dorothy" in sample
    assert "Hoops earrings pair plain 9K YG" in sample
    assert "€ 90.13" in sample


def test_rejects_non_pdf_upload():
    application.app.config["TESTING"] = True
    response = application.app.test_client().post("/api/process", data={
        "invoice": (io.BytesIO(b"not a pdf"), "invoice.txt"), "gold_fix": "65.20", "markup": "35", "gold_markup": "27",
    })
    assert response.status_code == 400
