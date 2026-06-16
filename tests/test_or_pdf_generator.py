from decimal import Decimal

from or_extractor.models import DocumentIndex, ExtractedLine, ExtractedList, RepairOrder
from or_extractor.or_pdf_generator import write_repair_order_pdf


def test_write_repair_order_pdf_creates_pdf(tmp_path):
    order = RepairOrder(
        document=DocumentIndex(
            res_id="39",
            client="VIRAMA MAYA",
            sinistre="F250487126A",
            expert="HELLO GILLES",
            immatriculation="FW-824-KL",
            date="25/12/2025",
            fields={
                "custom_t10": ["PORTE AV G"],
                "custom_t11": "Remplacement porte avant gauche",
                "custom_t12": "Peinture incluse",
            },
        ),
        extracted_list=ExtractedList(
            kind="fournitures",
            lines=[
                ExtractedLine(
                    quantity=None,
                    label="PORTE AV G",
                    reference=None,
                    operation="E P",
                    amount_ht=Decimal("1098.60"),
                )
            ],
            total_ht=Decimal("1098.60"),
        ),
    )
    path = tmp_path / "or_39.pdf"

    write_repair_order_pdf(order, path)

    content = path.read_bytes()
    assert content.startswith(b"%PDF-1.4")
    assert b"Travaux et observations" in content
    assert b"Remplacement porte avant gauche" in content
    assert b"Peinture incluse" in content
    assert b"%%EOF" in content[-20:]
