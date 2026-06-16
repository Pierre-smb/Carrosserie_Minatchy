from __future__ import annotations

import html
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import RepairOrder


def repair_order_to_dict(order: RepairOrder) -> dict[str, Any]:
    return _json_ready(asdict(order))


def write_repair_order_json(order: RepairOrder, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(repair_order_to_dict(order), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_repair_order_html(order: RepairOrder, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = repair_order_to_dict(order)
    doc = data["document"]
    extracted = data["extracted_list"]
    work_designation = _field_text(doc, "custom_t11", "customT11")
    observations = _field_text(doc, "custom_t12", "customT12")
    extra_sections = "\n".join(
        _html_note_section(label, value)
        for label, value in (
            ("Designation des travaux", work_designation),
            ("Observations", observations),
        )
        if value
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(line.get('quantity') or ''))}</td>"
        f"<td>{html.escape(line.get('label') or '')}</td>"
        f"<td>{html.escape(line.get('reference') or '')}</td>"
        f"<td>{html.escape(line.get('operation') or '')}</td>"
        f"<td class=\"amount\">{html.escape(str(line.get('amount_ht') or ''))}</td>"
        "</tr>"
        for line in extracted["lines"]
    )
    output_path.write_text(
        f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Ordre de reparation {html.escape(doc.get('res_id') or '')}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2933; }}
    h1 {{ font-size: 24px; margin: 0 0 24px; }}
    h2 {{ font-size: 16px; margin: 24px 0 8px; }}
    dl {{ display: grid; grid-template-columns: 170px 1fr; gap: 6px 16px; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #cfd7df; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; }}
    .amount {{ text-align: right; white-space: nowrap; }}
    h3 {{ font-size: 13px; margin: 14px 0 6px; }}
    .note {{ border: 1px solid #d8e0e8; background: #fbfcfd; padding: 10px; white-space: normal; }}
  </style>
</head>
<body>
  <h1>Ordre de reparation</h1>
  <h2>Indices PV</h2>
  <dl>
    <dt>Client</dt><dd>{html.escape(doc.get('client') or '')}</dd>
    <dt>Sinistre</dt><dd>{html.escape(doc.get('sinistre') or '')}</dd>
    <dt>Expert</dt><dd>{html.escape(doc.get('expert') or '')}</dd>
    <dt>Immatriculation</dt><dd>{html.escape(doc.get('immatriculation') or '')}</dd>
    <dt>Date</dt><dd>{html.escape(doc.get('date') or '')}</dd>
  </dl>
  <h2>Travaux et observations</h2>
  {extra_sections or '<p></p>'}
  <h2>Liste des {html.escape(extracted.get('kind') or '')}</h2>
  <table>
    <thead>
      <tr><th>Quantite</th><th>Libelle</th><th>Reference</th><th>Operation</th><th>Montant HT</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p><strong>Total HT:</strong> {html.escape(str(extracted.get('total_ht') or ''))}</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _html_note_section(label: str, value: str) -> str:
    text = html.escape(value).replace(chr(10), "<br>")
    return f"<h3>{html.escape(label)}</h3>\n<div class=\"note\">{text}</div>"


def _field_text(document: dict[str, Any], *keys: str) -> str:
    fields = document.get("fields")
    if not isinstance(fields, dict):
        return ""
    for key in keys:
        value = fields.get(key)
        if value not in (None, ""):
            return _stringify_field(value)
    return ""


def _stringify_field(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item not in (None, ""))
    return str(value)
