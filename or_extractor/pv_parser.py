from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .models import ExtractedLine, ExtractedList, ExtractedTextFields


SECTION_RE = re.compile(
    r"\bliste\s+des\s+(?P<kind>fournitures|pieces|pi[eè]ces)\b",
    re.IGNORECASE,
)
TOTAL_RE = re.compile(r"\btotal\b", re.IGNORECASE)
HEADER_WORDS_RE = re.compile(
    r"\b(qt[eé]|quantit[eé]|libell[eé]|r[eé]f[eé]rence|op[eé]ration|montant|ht)\b",
    re.IGNORECASE,
)
OPERATION_LABELS = {
    "E": "Echange",
    "R": "Reparation",
    "P": "Peinture",
    "D": "Depose/Repose",
    "C": "Controle",
    "G": "Reglage",
    "L": "Lustrage",
    "N": "Nettoyage",
}
AMOUNT_RE = re.compile(r"(?P<amount>-?\d{1,3}(?:[ .]\d{3})*(?:[,.]\d{2})|-?\d+[,.]\d{2})")
QUANTITY_RE = re.compile(r"^\s*(?P<qty>\d+(?:[,.]\d+)?)\s+")
REFERENCE_RE = re.compile(r"\b(?:ref(?:\.|erence)?|r[eé]f(?:\.|[eé]rence)?)\s*[:\-]?\s*(?P<ref>[A-Z0-9][A-Z0-9./_-]{2,})", re.IGNORECASE)
OPERATION_RE = re.compile(
    r"\b(?P<op>remplacement|reparation|r[eé]paration|peinture|depose|d[eé]pose|pose|controle|contr[oô]le|redressage)\b",
    re.IGNORECASE,
)


OBSERVATIONS_RE = re.compile(r"\bobservations?\b", re.IGNORECASE)
WORK_SECTION_RE = re.compile(
    r"\b(d[eÃ©]signation\s+des\s+travaux|travaux\s+(?:a|Ã )\s+effectuer)\b",
    re.IGNORECASE,
)
WORK_STOP_RE = re.compile(
    r"\b(liste\s+des\s+(?:fournitures|pieces|pi[eÃ¨]ces)|observations?|estimation\s+des\s+dommages)\b",
    re.IGNORECASE,
)
BOILERPLATE_RE = re.compile(
    r"\b(ce\s+document\s+ne\s+peut|toute\s+modification|r[eÃ©]f[eÃ©]rences\s+pi[eÃ¨]ces|signature\s*:|l'expert\s+le\s+r[eÃ©]parateur)\b",
    re.IGNORECASE,
)


class PvListNotFound(RuntimeError):
    pass


def parse_expert_report_pages(pages: list[str]) -> ExtractedList:
    section_kind: str | None = None
    collecting = False
    lines: list[ExtractedLine] = []
    total_ht: Decimal | None = None

    for page_number, page_text in enumerate(pages, start=1):
        raw_lines = [line.strip() for line in page_text.splitlines()]
        for raw_line in raw_lines:
            line = _normalize_spaces(raw_line)
            if not line:
                continue

            if not collecting:
                match = SECTION_RE.search(line)
                if not match:
                    continue
                section_kind = _normalize_kind(match.group("kind"))
                collecting = True
                trailing = line[match.end() :].strip(" :-")
                if not trailing:
                    continue
                line = trailing

            if _is_total_marker(line, lines):
                total_ht = _extract_total_ht(line)
                return ExtractedList(kind=section_kind or "pieces", lines=lines, total_ht=total_ht)

            if _is_table_noise(line):
                continue

            parsed = parse_alphaexpert_line(
                line,
                kind=section_kind or "pieces",
                page_number=page_number,
            )
            if parsed:
                lines.append(parsed)
            elif lines:
                previous = lines[-1]
                continuation = _clean_continuation(line)
                lines[-1] = ExtractedLine(
                    quantity=previous.quantity,
                    label=f"{previous.label} {continuation}".strip(),
                    reference=previous.reference,
                    operation=previous.operation,
                    amount_ht=previous.amount_ht,
                    page=previous.page,
                    raw=f"{previous.raw} {line}".strip(),
                )

    if not section_kind:
        raise PvListNotFound("Aucune section 'Liste des fournitures' ou 'Liste des pieces' detectee.")
    return ExtractedList(kind=section_kind, lines=lines, total_ht=total_ht)


def extract_text_fields(text: str, extracted_list: ExtractedList) -> ExtractedTextFields:
    lines = [_normalize_spaces(line) for line in text.splitlines()]
    return ExtractedTextFields(
        work_designation=_extract_work_designation(lines),
        observations=_extract_observations(lines),
        indexed_items=_format_indexed_items(extracted_list),
    )


def _extract_work_designation(lines: list[str]) -> str | None:
    explicit = _extract_explicit_work_section(lines)
    if explicit:
        return explicit

    for line in lines:
        left = _left_column(line)
        normalized = left.upper()
        if normalized.startswith("CONSTATES") or normalized.startswith("CONSTAT"):
            return left.strip(" :-") or None
    return None


def _extract_explicit_work_section(lines: list[str]) -> str | None:
    collecting = False
    values: list[str] = []
    for line in lines:
        left = _left_column(line)
        if not left:
            continue
        if not collecting:
            match = WORK_SECTION_RE.search(left)
            if not match:
                continue
            collecting = True
            trailing = left[match.end() :].strip(" :-")
            if trailing:
                values.append(trailing)
            continue
        if WORK_STOP_RE.search(left) or BOILERPLATE_RE.search(left):
            break
        values.append(left)
    return _join_section_lines(values)


def _extract_observations(lines: list[str]) -> str | None:
    collecting = False
    values: list[str] = []
    for line in lines:
        left = _left_column(line)
        if not left and not collecting:
            continue
        if not collecting:
            match = OBSERVATIONS_RE.search(left)
            if not match:
                continue
            collecting = True
            trailing = left[match.end() :].strip(" :-")
            if trailing:
                values.append(trailing)
            continue
        if BOILERPLATE_RE.search(left):
            break
        if TOTAL_RE.search(left) and "accord" not in left.lower():
            break
        if left:
            values.append(left.strip(" -"))
    return _join_section_lines(values)


def _format_indexed_items(extracted_list: ExtractedList) -> list[str]:
    return [line.label for line in extracted_list.lines if line.label]


def _left_column(line: str) -> str:
    return _normalize_spaces(line.split("!", 1)[0].strip(" -"))


def _join_section_lines(lines: list[str]) -> str | None:
    cleaned = []
    for line in lines:
        value = _normalize_spaces(line.strip(" -:;"))
        if value:
            cleaned.append(value)
    if not cleaned:
        return None
    return "\n".join(cleaned)


def parse_alphaexpert_line(
    line: str,
    kind: str,
    page_number: int | None = None,
) -> ExtractedLine | None:
    if kind == "pieces" and "!" in line:
        parsed = _parse_bang_delimited_piece_line(line, page_number)
        if parsed:
            return parsed
        if line.lstrip().startswith("!"):
            return None

    if kind == "fournitures":
        return _parse_fourniture_line(line, page_number)

    return parse_item_line(line, page_number=page_number)


def parse_item_line(line: str, page_number: int | None = None) -> ExtractedLine | None:
    original = line
    line = _normalize_spaces(line)
    amount = _extract_last_decimal(line)
    if amount is not None:
        amount_match = list(AMOUNT_RE.finditer(line))[-1]
        line = (line[: amount_match.start()] + line[amount_match.end() :]).strip()

    qty: Decimal | None = None
    qty_match = QUANTITY_RE.match(line)
    if qty_match:
        qty = _to_decimal(qty_match.group("qty"))
        line = line[qty_match.end() :].strip()

    reference = None
    ref_match = REFERENCE_RE.search(line)
    if ref_match:
        reference = ref_match.group("ref")
        line = (line[: ref_match.start()] + line[ref_match.end() :]).strip()

    operation = None
    op_match = OPERATION_RE.search(line)
    if op_match:
        operation = _normalize_operation(op_match.group("op"))

    label = _clean_label(line)
    if not label:
        return None
    if qty is None and amount is None and not _looks_like_item(label):
        return None

    return ExtractedLine(
        quantity=qty,
        label=label,
        reference=reference,
        operation=operation,
        amount_ht=amount,
        page=page_number,
        raw=original,
    )


def _parse_bang_delimited_piece_line(
    line: str,
    page_number: int | None,
) -> ExtractedLine | None:
    parts = [_normalize_spaces(part) for part in line.strip().strip("!").split("!")]
    parts = [part for part in parts if part != ""]
    if len(parts) < 2:
        return None
    if HEADER_WORDS_RE.search(" ".join(parts)):
        return None

    qty = _to_decimal(parts[0])
    if qty is None:
        return None

    label = parts[1]
    reference = None
    operation = None
    amount = None
    if len(parts) > 4:
        reference = parts[2] or None
        operation = _normalize_operation(parts[3]) if parts[3] else None
        amount = _to_decimal(parts[4]) if parts[4] else None
    elif len(parts) == 4:
        third = parts[2]
        fourth = parts[3]
        if _is_operation_code(third) and _to_decimal(fourth) is not None:
            operation = _normalize_operation(third)
            amount = _to_decimal(fourth)
        else:
            reference = third or None
            operation = _normalize_operation(fourth) if fourth else None
    elif len(parts) == 3:
        third = parts[2]
        if _to_decimal(third) is not None:
            amount = _to_decimal(third)
        elif _is_operation_code(third):
            operation = _normalize_operation(third)
        else:
            reference = third or None

    return ExtractedLine(
        quantity=qty,
        label=label,
        reference=reference,
        operation=operation,
        amount_ht=amount,
        page=page_number,
        raw=line,
    )


def _parse_fourniture_line(line: str, page_number: int | None) -> ExtractedLine | None:
    left_column = line.split("!", 1)[0].strip()
    if not left_column or _is_table_noise(left_column):
        return None
    left_lower = left_column.lower()
    if "libell" in left_lower and "prix" in left_lower:
        return None
    if set(left_column) <= {"-", "_", " ", "."}:
        return None

    amount_matches = list(AMOUNT_RE.finditer(left_column))
    if amount_matches:
        amount_match = amount_matches[-1]
        amount = _to_decimal(amount_match.group("amount"))
        before_amount = left_column[: amount_match.start()].strip()
        after_amount = left_column[amount_match.end() :].strip()
        operation = _normalize_operation(after_amount) if after_amount else None
        label = before_amount
    else:
        amount = None
        label, operation = _split_label_operation_without_amount(left_column)

    label = _clean_label(label)
    if not label or not _looks_like_item(label):
        return None

    return ExtractedLine(
        quantity=None,
        label=label,
        reference=None,
        operation=operation,
        amount_ht=amount,
        page=page_number,
        raw=line,
    )


def _split_label_operation_without_amount(value: str) -> tuple[str, str | None]:
    tokens = value.split()
    if len(tokens) >= 3 and tokens[-2:] in (["R", "P"], ["E", "P"], ["D", "P"]):
        return " ".join(tokens[:-2]), _normalize_operation(" ".join(tokens[-2:]))
    if len(tokens) >= 2 and tokens[-1] in {"E", "R", "D", "C", "P", "G", "L", "N", "EP", "PP", "RP"}:
        return " ".join(tokens[:-1]), _normalize_operation(tokens[-1])
    return value, None


def _normalize_operation(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_spaces(value).upper().replace(".", "")
    word_map = {
        "REMPLACEMENT": "Echange",
        "REPARATION": "Reparation",
        "PEINTURE": "Peinture",
    }
    if normalized in word_map:
        return word_map[normalized]

    compact = normalized.replace(" ", "")
    if compact and all(char in OPERATION_LABELS for char in compact):
        labels = []
        for char in compact:
            label = OPERATION_LABELS[char]
            if label not in labels:
                labels.append(label)
        return " + ".join(labels)

    labels = []
    for token in normalized.split():
        label = OPERATION_LABELS.get(token)
        if label and label not in labels:
            labels.append(label)
    if labels:
        return " + ".join(labels)
    return _normalize_spaces(value)


def _is_operation_code(value: str | None) -> bool:
    if not value:
        return False
    compact = _normalize_spaces(value).upper().replace(" ", "").replace(".", "")
    return bool(compact) and all(char in OPERATION_LABELS for char in compact)


def _normalize_kind(kind: str) -> str:
    normalized = kind.lower().replace("è", "e").replace("é", "e")
    return "fournitures" if "fourniture" in normalized else "pieces"


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_table_noise(line: str) -> bool:
    if HEADER_WORDS_RE.search(line) and not AMOUNT_RE.search(line):
        return True
    return len(line) <= 2 or set(line) <= {"-", "_", " ", "."}


def _is_total_marker(line: str, lines: list[ExtractedLine]) -> bool:
    if not lines:
        return False
    normalized = _normalize_spaces(line).upper()
    return (
        normalized.startswith("TOTAL")
        or normalized.startswith("! TOTAL")
        or "TOTAL FOURNITURES" in normalized
        or "TOTAL PIECES" in normalized
        or "TOTAL PIÈCES" in normalized
    )


def _extract_last_decimal(line: str) -> Decimal | None:
    matches = list(AMOUNT_RE.finditer(line))
    if not matches:
        return None
    return _to_decimal(matches[-1].group("amount"))


def _extract_total_ht(line: str) -> Decimal | None:
    match = re.search(
        r"\btotal(?:\s+\w+)*\b.*?(?P<amount>-?\d{1,3}(?:[ .]\d{3})*(?:[,.]\d{2})|-?\d+[,.]\d{2})\s*(?:h\.?t\.?|ht)\b",
        line,
        flags=re.IGNORECASE,
    )
    if match:
        return _to_decimal(match.group("amount"))
    return _extract_last_decimal(line)


def _to_decimal(value: str) -> Decimal | None:
    normalized = value.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _clean_label(line: str) -> str:
    line = re.sub(r"\b(ref(?:\.|erence)?|r[eé]f(?:\.|[eé]rence)?)\s*[:\-]?", "", line, flags=re.IGNORECASE)
    return _normalize_spaces(line.strip(" -;:"))


def _clean_continuation(line: str) -> str:
    return _normalize_spaces(line.strip(" !-;:"))


def _looks_like_item(label: str) -> bool:
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3,}", label))
