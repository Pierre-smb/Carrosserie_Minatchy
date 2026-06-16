from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_WANTED_COLUMNS = (
    "Res_Id,Upload_Id,"
    "custom_t2,custom_t3,custom_t4,custom_t5,custom_d4,custom_d1,"
    "custom_t6,custom_t8,custom_t1,custom_t7,custom_t9,"
    "custom_t10,custom_t11,custom_t12"
)

FIELD_LABEL_TO_INDEX_ID = {
    "Informations Générales|Client": "custom_t2",
    "Informations Générales|Référence du document": "custom_t3",
    "Informations Générales| N° de police": "custom_t4",
    "Informations Générales| N° de sinistre": "custom_t5",
    "Informations Générales|Date du sinistre": "custom_d4",
    "Informations Générales|Date visite expert": "custom_d1",
    "Informations Générales| Nom de l'expert": "custom_t6",
    "Informations Générales|Nom de l'assurance": "custom_t8",
    "Informations Générales|Immatriculation véhicule": "custom_t1",
    "Informations Générales| Modèle du véhicule": "custom_t7",
    "Informations Générales|Adresse du client": "custom_t9",
}


@dataclass(frozen=True)
class ZeendocSettings:
    base_url: str
    login: str
    password: str
    binder_id: str
    wanted_columns: str = DEFAULT_WANTED_COLUMNS
    line_config_file_name: str | None = None
    search_id: str | None = "24"
    or_source_id: int | None = None
    or_document_type_field: str = "custom_n3"
    or_document_type_value: str = "18"
    processed_field: str = "custom_n1"
    processed_value: str = "1"

    @classmethod
    def from_env(cls) -> "ZeendocSettings":
        missing = [
            name
            for name in (
                "ZEENDOC_BASE_URL",
                "ZEENDOC_LOGIN",
                "ZEENDOC_PASSWORD",
                "ZEENDOC_BINDER_ID",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "Variables d'environnement manquantes: " + ", ".join(missing)
            )

        return cls(
            base_url=normalize_zeendoc_base_url(os.environ["ZEENDOC_BASE_URL"]),
            login=os.environ["ZEENDOC_LOGIN"],
            password=os.environ["ZEENDOC_PASSWORD"],
            binder_id=normalize_zeendoc_binder_id(os.environ["ZEENDOC_BINDER_ID"]),
            wanted_columns=normalize_wanted_columns(
                os.getenv("ZEENDOC_WANTED_COLUMNS", DEFAULT_WANTED_COLUMNS)
            ),
            line_config_file_name=os.getenv("ZEENDOC_LINE_CONFIG") or None,
            search_id=os.getenv("ZEENDOC_SEARCH_ID") or "24",
            or_source_id=_optional_int(os.getenv("ZEENDOC_OR_SOURCE_ID")),
            or_document_type_field=os.getenv("ZEENDOC_OR_DOCUMENT_TYPE_FIELD") or "custom_n3",
            or_document_type_value=os.getenv("ZEENDOC_OR_DOCUMENT_TYPE_VALUE") or "18",
            processed_field=os.getenv("ZEENDOC_PROCESSED_FIELD") or "custom_n1",
            processed_value=os.getenv("ZEENDOC_PROCESSED_VALUE") or "1",
        )


def normalize_zeendoc_base_url(value: str) -> str:
    base_url = value.rstrip("/")
    if base_url.endswith("/api"):
        return base_url + "/v4"
    if base_url.endswith("/api/v4") or "/api/" in base_url:
        return base_url
    return base_url + "/api/v4"


def normalize_zeendoc_binder_id(value: str) -> str:
    binder_id = value.strip()
    if binder_id.isdigit():
        return f"coll_{binder_id}"
    return binder_id


def normalize_wanted_columns(value: str) -> str:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    normalized: list[str] = []
    for column in columns:
        normalized.append(FIELD_LABEL_TO_INDEX_ID.get(column, column))

    if normalized == ["Res_Id", "Upload_Id"]:
        return DEFAULT_WANTED_COLUMNS

    seen = set()
    deduped = []
    for column in normalized:
        if column not in seen:
            seen.add(column)
            deduped.append(column)
    return ",".join(deduped)


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
