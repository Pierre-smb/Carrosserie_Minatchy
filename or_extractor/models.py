from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DocumentIndex:
    res_id: str
    upload_id: str | None = None
    client: str | None = None
    sinistre: str | None = None
    expert: str | None = None
    immatriculation: str | None = None
    date: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedLine:
    quantity: Decimal | None
    label: str
    reference: str | None = None
    operation: str | None = None
    amount_ht: Decimal | None = None
    page: int | None = None
    raw: str = ""


@dataclass(frozen=True)
class ExtractedList:
    kind: str
    lines: list[ExtractedLine]
    total_ht: Decimal | None = None


@dataclass(frozen=True)
class ExtractedTextFields:
    work_designation: str | None = None
    observations: str | None = None
    indexed_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RepairOrder:
    document: DocumentIndex
    extracted_list: ExtractedList
