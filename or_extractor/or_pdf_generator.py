from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from .models import RepairOrder


A4_WIDTH = 595
A4_HEIGHT = 842
MARGIN = 36
LINE_HEIGHT = 12
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo-minatchy.jpg"
VEHICLE_IMPACT_PATH = Path(__file__).resolve().parent.parent / "assets" / "vehicle-impact.jpg"
CGV_PATH = Path(__file__).resolve().parent.parent / "assets" / "cgv.txt"
LOGO_WIDTH = 158
LOGO_HEIGHT = 61
SIGNATURE_TOP_Y = 206
CGV_TOP_Y = 106
CGV_HEIGHT = 54
VEHICLE_DIAGRAM_TOP_Y = 428
VEHICLE_DIAGRAM_HEIGHT = 174


@dataclass
class PdfPage:
    commands: list[str]


def write_repair_order_pdf(order: RepairOrder, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pages = _build_pages(order)
    output_path.write_bytes(_render_pdf(pages))


def _build_pages(order: RepairOrder) -> list[PdfPage]:
    pages = [PdfPage(commands=[])]
    y = A4_HEIGHT - MARGIN

    def page() -> PdfPage:
        return pages[-1]

    def new_page() -> None:
        nonlocal y
        pages.append(PdfPage(commands=[]))
        y = A4_HEIGHT - MARGIN
        _draw_page_frame(page(), len(pages))

    def ensure_space(height: int) -> None:
        if y - height < MARGIN + 24:
            new_page()

    _draw_page_frame(page(), 1)
    _draw_header(page(), order)
    y = A4_HEIGHT - 160

    doc = order.document
    metadata = [
        ("Client", doc.client),
        ("Sinistre", doc.sinistre),
        ("Expert", doc.expert),
        ("Immatriculation", doc.immatriculation),
        ("Date", doc.date),
        ("Document Zeendoc", doc.res_id),
    ]
    _section_title(page(), MARGIN, y, "Informations dossier")
    y -= 22
    _info_grid(page(), MARGIN, y, metadata)
    y -= 58

    complement_rows = [
        ("Designation des travaux", _field_text(doc.fields, "custom_t11", "customT11")),
        ("Observations", _field_text(doc.fields, "custom_t12", "customT12")),
    ]
    complement_rows = [(label, value) for label, value in complement_rows if value]
    if complement_rows:
        y -= 8
        ensure_space(34)
        _section_title(page(), MARGIN, y, "Travaux et observations")
        y -= 22
        for label, value in complement_rows:
            wrapped = _wrap_multiline(value, 94)
            box_height = max(30, 16 + len(wrapped) * LINE_HEIGHT)
            ensure_space(box_height + 8)
            _fill_rect(page(), MARGIN, y - box_height, A4_WIDTH - MARGIN * 2, box_height, "0.98 0.99 1.00")
            _rect(page(), MARGIN, y - box_height, A4_WIDTH - MARGIN * 2, box_height, color="0.84 0.88 0.92")
            _text(page(), MARGIN + 8, y - 12, label, size=8, bold=True, color="0.10 0.45 0.60")
            _multiline_text(page(), MARGIN + 8, y - 26, "\n".join(wrapped), width=500, size=8)
            y -= box_height + 8

    y -= 12
    _section_title(page(), MARGIN, y, f"Liste des {order.extracted_list.kind}")
    y -= 18

    columns = [
        ("Qte", 34),
        ("Libelle", 210),
        ("Reference", 76),
        ("Operation", 112),
        ("Montant HT", 62),
    ]
    table_width = sum(width for _, width in columns)

    def draw_header() -> None:
        nonlocal y
        ensure_space(26)
        _fill_rect(page(), MARGIN, y - 16, table_width, 18, "0.10 0.45 0.60")
        x = MARGIN + 4
        for title, width in columns:
            _text(page(), x, y - 11, title, size=8, bold=True, color="1 1 1")
            x += width
        y -= 18

    draw_header()
    for line in order.extracted_list.lines:
        wrapped_label = _wrap(str(line.label or ""), 38)
        row_height = max(18, len(wrapped_label) * LINE_HEIGHT + 6)
        ensure_space(row_height + 18)
        if y < MARGIN + row_height + 24:
            draw_header()

        _rect(page(), MARGIN, y - row_height, table_width, row_height, color="0.78 0.82 0.86")
        values = [
            _format_quantity(line.quantity),
            "\n".join(wrapped_label),
            line.reference or "",
            line.operation or "",
            _format_amount(line.amount_ht),
        ]
        x = MARGIN + 4
        for value, (title, width) in zip(values, columns):
            text_width = width - 8
            if title in {"Reference", "Operation"}:
                value = _fit_text(value, text_width)
            if title == "Montant HT":
                _text(page(), x + 2, y - 11, _fit_text(value, text_width), size=8)
            else:
                _multiline_text(page(), x, y - 11, value, width=text_width, size=8)
            x += width
        y -= row_height

    y -= 18
    ensure_space(20)
    _fill_rect(page(), MARGIN + table_width - 170, y - 14, 170, 22, "0.95 0.97 0.98")
    _rect(page(), MARGIN + table_width - 170, y - 14, 170, 22, color="0.10 0.45 0.60")
    _text(page(), MARGIN + table_width - 160, y - 6, "Total HT", size=10, bold=True, color="0.10 0.45 0.60")
    _text(page(), MARGIN + table_width - 72, y - 6, _format_amount(order.extracted_list.total_ht), size=10, bold=True)

    y -= 30
    if y < VEHICLE_DIAGRAM_TOP_Y + 18:
        new_page()
    _vehicle_impact_diagram(page(), MARGIN, VEHICLE_DIAGRAM_TOP_Y)
    _signature_boxes(page(), MARGIN, SIGNATURE_TOP_Y)
    _cgv_box(page(), MARGIN, CGV_TOP_Y)

    return pages


def _render_pdf(pages: list[PdfPage]) -> bytes:
    objects: list[bytes] = []
    catalog_id = 1
    pages_id = 2
    font_regular_id = 3
    font_bold_id = 4
    next_id = 5
    logo_id = next_id if LOGO_PATH.exists() else None
    if logo_id:
        next_id += 1
    vehicle_id = next_id if VEHICLE_IMPACT_PATH.exists() else None
    if vehicle_id:
        next_id += 1
    page_object_ids: list[int] = []

    for pdf_page in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_object_ids.append(page_id)
        stream = "\n".join(pdf_page.commands).encode("cp1252", errors="replace")
        objects.append(
            _obj(
                content_id,
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
            )
        )
        objects.append(
            _obj(
                page_id,
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {A4_WIDTH} {A4_HEIGHT}] "
                    f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> "
                    f"{_image_resources(logo_id, vehicle_id)}>> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
            )
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects.insert(0, _obj(font_bold_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"))
    objects.insert(0, _obj(font_regular_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"))
    if logo_id:
        objects.insert(0, _image_object(logo_id, LOGO_PATH, 674, 260))
    if vehicle_id:
        objects.insert(0, _image_object(vehicle_id, VEHICLE_IMPACT_PATH, 791, 900))
    objects.insert(0, _obj(pages_id, f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii")))
    objects.insert(0, _obj(catalog_id, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")))

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in sorted(objects, key=lambda value: int(value.split(b" ", 1)[0])):
        offsets.append(len(output))
        output.extend(obj)
        output.extend(b"\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _obj(object_id: int, body: bytes) -> bytes:
    return str(object_id).encode("ascii") + b" 0 obj\n" + body + b"\nendobj"


def _image_resources(logo_id: int | None, vehicle_id: int | None) -> str:
    resources = []
    if logo_id:
        resources.append(f"/ImLogo {logo_id} 0 R")
    if vehicle_id:
        resources.append(f"/ImVehicle {vehicle_id} 0 R")
    if not resources:
        return ""
    return "/XObject << " + " ".join(resources) + " >> "


def _image_object(object_id: int, path: Path, width: int, height: int) -> bytes:
    data = path.read_bytes()
    body = (
        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
        f"/Length {len(data)} >>\nstream\n"
    ).encode("ascii") + data + b"\nendstream"
    return _obj(object_id, body)


def _text(
    page: PdfPage,
    x: int,
    y: int,
    text: str,
    size: int = 10,
    bold: bool = False,
    color: str = "0.12 0.16 0.20",
) -> None:
    font = "F2" if bold else "F1"
    page.commands.append(f"{color} rg BT /{font} {size} Tf {x} {y} Td ({_escape_text(text)}) Tj ET")


def _multiline_text(page: PdfPage, x: int, y: int, text: str, width: int, size: int = 8) -> None:
    lines = text.splitlines() or [""]
    for index, line in enumerate(lines):
        _text(page, x, y - index * LINE_HEIGHT, line[: max(1, width)], size=size)


def _rect(page: PdfPage, x: int, y: int, width: int, height: int, color: str = "0.12 0.16 0.20") -> None:
    page.commands.append(f"{color} RG {x} {y} {width} {height} re S")


def _fill_rect(page: PdfPage, x: int, y: int, width: int, height: int, color: str) -> None:
    page.commands.append(f"{color} rg {x} {y} {width} {height} re f")


def _draw_page_frame(page: PdfPage, page_number: int) -> None:
    _fill_rect(page, 0, A4_HEIGHT - 8, A4_WIDTH, 8, "0.10 0.45 0.60")
    _fill_rect(page, 0, A4_HEIGHT - 13, A4_WIDTH, 5, "0.93 0.05 0.08")
    _text(page, A4_WIDTH - MARGIN - 54, 18, f"Page {page_number}", size=8, color="0.45 0.50 0.55")


def _draw_header(page: PdfPage, order: RepairOrder) -> None:
    top = A4_HEIGHT - MARGIN
    if LOGO_PATH.exists():
        page.commands.append(f"q {LOGO_WIDTH} 0 0 {LOGO_HEIGHT} {MARGIN} {top - LOGO_HEIGHT} cm /ImLogo Do Q")
    else:
        _text(page, MARGIN, top - 28, "CARROSSERIE MINATCHY", size=18, bold=True, color="0.10 0.45 0.60")
    _text(page, A4_WIDTH - MARGIN - 210, top - 8, "ORDRE DE REPARATION", size=18, bold=True, color="0.10 0.45 0.60")
    _text(page, A4_WIDTH - MARGIN - 210, top - 28, f"Document Zeendoc n° {order.document.res_id}", size=9, color="0.45 0.50 0.55")
    _text(page, A4_WIDTH - MARGIN - 210, top - 44, "Carrosserie Cyril Minatchy", size=9, bold=True)
    _text(page, A4_WIDTH - MARGIN - 210, top - 58, "32 rue Colbert - 97460 Saint-Paul", size=8, color="0.45 0.50 0.55")
    _fill_rect(page, MARGIN, top - 88, A4_WIDTH - MARGIN * 2, 1, "0.78 0.82 0.86")


def _section_title(page: PdfPage, x: int, y: int, title: str) -> None:
    _fill_rect(page, x, y - 14, 4, 18, "0.93 0.05 0.08")
    _text(page, x + 10, y - 9, title, size=12, bold=True, color="0.10 0.45 0.60")


def _info_grid(page: PdfPage, x: int, y: int, rows: list[tuple[str, object]]) -> None:
    col_width = 258
    row_height = 18
    for index, (label, value) in enumerate(rows):
        col = index % 2
        row = index // 2
        cell_x = x + col * col_width
        cell_y = y - row * row_height
        _fill_rect(page, cell_x, cell_y - 13, 92, 16, "0.95 0.97 0.98")
        _rect(page, cell_x, cell_y - 13, col_width - 8, 16, color="0.86 0.89 0.92")
        _text(page, cell_x + 5, cell_y - 8, label, size=8, bold=True, color="0.45 0.50 0.55")
        _text(page, cell_x + 98, cell_y - 8, str(value or ""), size=8)


def _signature_boxes(page: PdfPage, x: int, y: int) -> None:
    box_width = 245
    box_height = 78
    gap = 33
    labels = ("Signature client", "Signature reparateur")
    for index, label in enumerate(labels):
        box_x = x + index * (box_width + gap)
        _fill_rect(page, box_x, y - box_height, box_width, box_height, "0.98 0.99 1.00")
        _rect(page, box_x, y - box_height, box_width, box_height, color="0.74 0.79 0.84")
        _text(page, box_x + 10, y - 16, label, size=9, bold=True, color="0.10 0.45 0.60")
        _text(page, box_x + 10, y - 34, "Date :", size=8, color="0.45 0.50 0.55")
        _fill_rect(page, box_x + 10, y - 60, box_width - 20, 1, "0.74 0.79 0.84")


def _vehicle_impact_diagram(page: PdfPage, x: int, y: int) -> None:
    width = A4_WIDTH - MARGIN * 2
    height = VEHICLE_DIAGRAM_HEIGHT
    _fill_rect(page, x, y - height, width, height, "0.98 0.99 1.00")
    _rect(page, x, y - height, width, height, color="0.82 0.86 0.90")
    _fill_rect(page, x, y - 28, width, 28, "0.10 0.45 0.60")
    _text(page, x + 12, y - 18, "Reperage des points de choc", size=10, bold=True, color="1 1 1")
    _text(page, x + width - 198, y - 18, "Entourer les zones concernees", size=7, color="0.88 0.95 0.98")

    if VEHICLE_IMPACT_PATH.exists():
        image_height = 132
        image_width = 116
        image_x = x + (width - image_width) / 2
        image_y = y - 158
        page.commands.append(
            f"q {image_width} 0 0 {image_height} {image_x:.1f} {image_y:.1f} cm /ImVehicle Do Q"
        )
        return

    car_x = x + 204
    car_top = y - 46
    car_width = 116
    car_height = 118
    _fill_rect(page, car_x - 12, car_top - car_height - 12, car_width + 24, car_height + 34, "1 1 1")
    _rect(page, car_x - 12, car_top - car_height - 12, car_width + 24, car_height + 34, color="0.86 0.89 0.92")
    _car_outline(page, car_x, car_top, car_width, car_height)
    _text(page, car_x + 48, car_top + 12, "AV", size=7, bold=True, color="0.45 0.50 0.55")
    _text(page, car_x + 47, car_top - car_height - 8, "AR", size=7, bold=True, color="0.45 0.50 0.55")

    left_zones = (
        ("AVG", "Avant gauche"),
        ("G", "Cote gauche"),
        ("ARG", "Arriere gauche"),
        ("AV", "Avant"),
    )
    right_zones = (
        ("AVD", "Avant droit"),
        ("D", "Cote droit"),
        ("ARD", "Arriere droit"),
        ("AR", "Arriere"),
    )
    for index, (code, label) in enumerate(left_zones):
        _zone_chip(page, x + 18, y - 54 - index * 28, code, label)
    for index, (code, label) in enumerate(right_zones):
        _zone_chip(page, x + width - 156, y - 54 - index * 28, code, label)

    _line(page, x + 150, y - 88, car_x - 15, y - 88, "0.82 0.86 0.90")
    _line(page, car_x + car_width + 15, y - 88, x + width - 168, y - 88, "0.82 0.86 0.90")


def _checkbox(page: PdfPage, x: int, y: int) -> None:
    _rect(page, x, y - 11, 9, 9, color="0.45 0.50 0.55")


def _zone_chip(page: PdfPage, x: int, y: int, code: str, label: str) -> None:
    width = 138
    height = 20
    _fill_rect(page, x, y - height, width, height, "1 1 1")
    _rect(page, x, y - height, width, height, color="0.82 0.86 0.90")
    _checkbox(page, x + 7, y - 4)
    _text(page, x + 24, y - 12, code, size=7, bold=True, color="0.10 0.45 0.60")
    _text(page, x + 52, y - 12, label, size=7, color="0.45 0.50 0.55")


def _car_outline(page: PdfPage, x: int, y: int, width: int, height: int) -> None:
    left = x + 16
    right = x + width - 16
    center = x + width / 2
    top = y - 6
    bottom = y - height + 6
    page.commands.append(
        "0.12 0.16 0.20 RG 1.2 w "
        f"{center:.1f} {top:.1f} m "
        f"{right:.1f} {top - 6:.1f} {right + 6:.1f} {top - 24:.1f} {right:.1f} {top - 38:.1f} c "
        f"{right - 2:.1f} {bottom + 18:.1f} {right - 10:.1f} {bottom + 4:.1f} {center:.1f} {bottom:.1f} c "
        f"{left + 10:.1f} {bottom + 4:.1f} {left + 2:.1f} {bottom + 18:.1f} {left:.1f} {top - 38:.1f} c "
        f"{left - 6:.1f} {top - 24:.1f} {left:.1f} {top - 6:.1f} {center:.1f} {top:.1f} c S"
    )
    _fill_rect(page, x + 27, y - 31, 32, 1, "0.45 0.50 0.55")
    _fill_rect(page, x + 27, y - 58, 32, 1, "0.45 0.50 0.55")
    _rect(page, x + 26, y - 31, 34, 26, color="0.45 0.50 0.55")
    _rect(page, x + 24, y - 72, 38, 32, color="0.45 0.50 0.55")
    _fill_rect(page, x + 2, y - 35, 7, 22, "0.12 0.16 0.20")
    _fill_rect(page, x + width - 9, y - 35, 7, 22, "0.12 0.16 0.20")
    _fill_rect(page, x + 2, y - 86, 7, 22, "0.12 0.16 0.20")
    _fill_rect(page, x + width - 9, y - 86, 7, 22, "0.12 0.16 0.20")


def _cgv_box(page: PdfPage, x: int, y: int) -> None:
    text = _load_cgv_text()
    _fill_rect(page, x, y - CGV_HEIGHT, A4_WIDTH - MARGIN * 2, CGV_HEIGHT, "0.99 0.99 0.99")
    _rect(page, x, y - CGV_HEIGHT, A4_WIDTH - MARGIN * 2, CGV_HEIGHT, color="0.82 0.86 0.90")
    _text(page, x + 8, y - 12, "CGV", size=7, bold=True, color="0.45 0.50 0.55")
    wrapped = _wrap_multiline(text, 128)[:3]
    _multiline_text(page, x + 8, y - 25, "\n".join(wrapped), width=520, size=6)


def _load_cgv_text() -> str:
    if CGV_PATH.exists():
        value = CGV_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "Conditions generales de vente disponibles sur demande."


def _escape_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _line(page: PdfPage, x1: float, y1: float, x2: float, y2: float, color: str = "0.12 0.16 0.20") -> None:
    page.commands.append(f"{color} RG {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")


def _wrap(value: str, width: int) -> list[str]:
    return textwrap.wrap(value, width=width, break_long_words=False) or [""]


def _wrap_multiline(value: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in value.splitlines() or [""]:
        lines.extend(_wrap(raw_line, width))
    return lines or [""]


def _field_text(fields: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = fields.get(key)
        if value not in (None, ""):
            return _stringify_field(value)
    return ""


def _stringify_field(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _format_quantity(value: object) -> str:
    return "" if value in (None, "") else str(value)


def _format_amount(value: object) -> str:
    return "" if value in (None, "") else str(value)


def _fit_text(value: object, width: int) -> str:
    text = "" if value in (None, "") else str(value)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "."
