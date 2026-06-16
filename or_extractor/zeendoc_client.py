from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin

import requests

from .models import DocumentIndex


class ZeendocApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZeendocDocument:
    index: DocumentIndex
    payload: dict[str, Any]


class ZeendocClient:
    def __init__(
        self,
        base_url: str,
        login: str,
        password: str,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.login = login
        self.password = password
        self.session = session or requests.Session()

    def authenticate(self) -> None:
        response = self.session.post(
            urljoin(self.base_url, "login"),
            json={"login": self.login, "password": self.password},
            timeout=30,
        )
        self._raise_for_status(response)
        cookie = response.json().get("cookie")
        if not cookie:
            return
        name, _, value = cookie.partition("=")
        if name and value:
            self.session.cookies.set(name, value)
        else:
            self.session.headers.update({"Cookie": cookie})

    def iter_documents(
        self,
        binder_id: str,
        wanted_columns: str,
        query: str | None = None,
        limit: int | None = None,
        line_config_file_name: str | None = None,
        search_id: str | None = None,
    ) -> Iterator[ZeendocDocument]:
        for item in self._iter_search_document_items(
            binder_id=binder_id,
            wanted_columns=wanted_columns,
            query=query,
            limit=limit,
            search_id=search_id,
        ):
            res_id = str(_first_present(item, "Res_Id", "resId", "ResId", "id") or "")
            upload_id = _first_present(item, "Upload_Id", "uploadId", "UploadId")
            if not res_id and not upload_id:
                continue
            detail = self.get_document(
                binder_id=binder_id,
                res_id=res_id or None,
                upload_id=upload_id,
                wanted_columns=wanted_columns,
                line_config_file_name=line_config_file_name,
            )
            yield _merge_document_payloads(item, detail.payload)

    def list_saved_queries(self, binder_id: str, nb_result: bool = True) -> dict[str, Any]:
        response = self.session.get(
            urljoin(self.base_url, f"binders/{binder_id}/saved-queries"),
            params={"nbResult": str(nb_result).lower()},
            timeout=60,
        )
        self._raise_for_status(response)
        payload = response.json()
        return payload

    def get_context(self, get_config_sets: bool = False) -> dict[str, Any]:
        response = self.session.get(
            urljoin(self.base_url, "context"),
            params={"getConfigSets": str(get_config_sets).lower()},
            timeout=60,
        )
        self._raise_for_status(response)
        return response.json()

    def list_binder_fields(self, binder_id: str) -> list[dict[str, Any]]:
        context = self.get_context()
        for collection in context.get("collections", []):
            if str(collection.get("collId")) == str(binder_id):
                return [item for item in collection.get("index", []) if isinstance(item, dict)]
        return []

    def get_document(
        self,
        binder_id: str,
        res_id: str | None = None,
        upload_id: str | None = None,
        wanted_columns: str | None = None,
        line_config_file_name: str | None = None,
    ) -> ZeendocDocument:
        params: dict[str, Any] = {"urlIndependent": "true"}
        if res_id:
            params["resId"] = res_id
        if upload_id:
            params["uploadId"] = upload_id
        if wanted_columns:
            params["wantedColumns"] = wanted_columns
        if line_config_file_name:
            params["lineConfigFileName"] = line_config_file_name

        response = self.session.get(
            urljoin(self.base_url, f"binders/{binder_id}/documents"),
            params=params,
            timeout=60,
        )
        self._raise_for_status(response)
        payload = response.json()
        document_payload = _unwrap_single_document(payload)
        self._dump_debug_payload(document_payload)
        return ZeendocDocument(
            index=_document_index_from_payload(document_payload),
            payload=document_payload,
        )

    def get_document_text(self, document: ZeendocDocument) -> str:
        coll_id = _document_coll_id(document)
        res_id = document.index.res_id
        if not coll_id or not res_id:
            raise ZeendocApiError(
                f"Impossible de recuperer le texte OCR: collId/resId manquant pour {res_id or 'document'}."
            )
        response = self.session.get(
            _cabinet_url(
                self.base_url,
                "Ihm/View/Get_Texte_Document.php",
            ),
            params={"Coll_Id": coll_id, "Res_Id": res_id},
            timeout=120,
        )
        self._raise_for_status(response)
        response.encoding = response.encoding or "utf-8"
        return response.text

    def upload_document(
        self,
        binder_id: str,
        file_path: Path,
        source_id: int | None = None,
        indexation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = file_path.read_bytes()
        payload: dict[str, Any] = {
            "fileName": file_path.name,
            "base64Document": base64.b64encode(content).decode("ascii"),
            "hash": hashlib.sha3_256(content).hexdigest(),
        }
        if source_id is not None:
            payload["sourceId"] = source_id
        if indexation:
            payload["indexation"] = indexation
        response = self.session.post(
            urljoin(self.base_url, f"binders/{binder_id}/documents"),
            json=payload,
            timeout=120,
        )
        self._raise_for_status(response)
        return response.json()

    def update_document_indexes(
        self,
        binder_id: str,
        res_id: str,
        indexes: dict[str, Any],
    ) -> dict[str, Any]:
        index_list = [
            {"label": label, "value": value}
            for label, value in indexes.items()
            if value not in (None, "")
        ]
        if not index_list:
            return {}
        response = self.session.patch(
            urljoin(self.base_url, f"binders/{binder_id}/documents/{res_id}/indexes"),
            json={"indexList": index_list},
            timeout=60,
        )
        self._raise_for_status(response)
        if not response.text:
            return {}
        return response.json()

    def _iter_search_document_items(
        self,
        binder_id: str,
        wanted_columns: str,
        query: str | None,
        limit: int | None,
        search_id: str | None,
    ) -> Iterator[dict[str, Any]]:
        page_size = min(limit or 100, 1000)
        offset = 0
        yielded = 0
        while True:
            payload = self._search_documents(
                binder_id=binder_id,
                wanted_columns=wanted_columns,
                query=query,
                search_id=search_id,
                offset=offset,
                page_size=page_size,
            )
            items = _extract_document_items(payload)
            if not items:
                return
            for item in items:
                if limit is not None and yielded >= limit:
                    return
                yielded += 1
                yield item

            nb_docs = _first_present(payload, "nbDocs", "NbDocs", "nb_docs")
            offset += len(items)
            if nb_docs is not None and offset >= int(nb_docs):
                return
            if len(items) < page_size:
                return

    def _search_documents(
        self,
        binder_id: str,
        wanted_columns: str,
        query: str | None,
        search_id: str | None,
        offset: int,
        page_size: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "from": offset,
            "nbResults": page_size,
            "wantedColumns": wanted_columns,
            "urlIndependent": True,
        }
        if query:
            body["savedQueryName"] = query
        if search_id:
            body["savedQueryId"] = int(search_id)

        response = self.session.post(
            urljoin(self.base_url, f"binders/{binder_id}/documents/search"),
            json=body,
            timeout=60,
        )
        self._raise_for_status(response)
        return response.json()

    def _dump_debug_payload(self, payload: dict[str, Any]) -> None:
        debug_dir = os.getenv("ZEENDOC_DEBUG_PAYLOAD_DIR")
        if not debug_dir:
            return
        document_id = str(_first_present(payload, "Res_Id", "resId", "ResId", "id") or "document")
        path = Path(debug_dir) / f"zeendoc_document_{document_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _dump_debug_search_payload(self, payload: dict[str, Any], offset: int) -> None:
        debug_dir = os.getenv("ZEENDOC_DEBUG_PAYLOAD_DIR")
        if not debug_dir:
            return
        path = Path(debug_dir) / f"zeendoc_search_{offset}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            hint = ""
            if response.status_code == 404 and response.url.rstrip("/").endswith("/login"):
                hint = (
                    " Verifiez ZEENDOC_BASE_URL: l'URL API doit pointer vers /api/v4 "
                    "(ex: https://armoires.zeendoc.com/votre_armoire/api/v4)."
                )
            raise ZeendocApiError(
                f"Erreur API Zeendoc {response.status_code}: {response.text[:500]}{hint}"
            ) from exc


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    lower_map = {key.lower(): value for key, value in payload.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _cabinet_url(base_url: str, path: str) -> str:
    marker = "/api/"
    root = base_url.rstrip("/")
    if marker in root:
        root = root.split(marker, 1)[0]
    return urljoin(root.rstrip("/") + "/", path.lstrip("/"))


def _document_coll_id(document: ZeendocDocument) -> str | None:
    value = _first_present(document.payload, "collId", "Coll_Id", "coll_id")
    if isinstance(value, str):
        return value
    if value is not None:
        return str(value)
    raw_value = _first_present(document.index.raw, "collId", "Coll_Id", "coll_id")
    if isinstance(raw_value, str):
        return raw_value
    if raw_value is not None:
        return str(raw_value)
    return None


def _merge_document_payloads(search_payload: dict[str, Any], detail_payload: dict[str, Any]) -> ZeendocDocument:
    merged = dict(search_payload)
    merged.update(detail_payload)
    for key in ("indexes", "properties"):
        if not merged.get(key) and search_payload.get(key):
            merged[key] = search_payload[key]
    return ZeendocDocument(index=_document_index_from_payload(merged), payload=merged)


def _payload_keys(payload: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)
            keys.append(full_key)
            if isinstance(value, (dict, list)):
                keys.extend(_payload_keys(value, full_key))
    elif isinstance(payload, list):
        for index, value in enumerate(payload[:3]):
            keys.extend(_payload_keys(value, f"{prefix}[{index}]"))
    return keys


def _extract_document_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("document", "documents", "Document", "Documents", "results", "Results", "data", "Data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    if any(key.lower() in {"res_id", "resid", "upload_id", "uploadid"} for key in payload):
        return [payload]
    return []


def _unwrap_single_document(payload: dict[str, Any]) -> dict[str, Any]:
    items = _extract_document_items(payload)
    if len(items) == 1:
        merged = dict(payload)
        merged.update(items[0])
        return merged
    return payload


def _document_index_from_payload(payload: dict[str, Any]) -> DocumentIndex:
    fields = _extract_index_values(payload)
    return DocumentIndex(
        res_id=str(_first_present(payload, "Res_Id", "resId", "ResId", "id") or ""),
        upload_id=_first_present(payload, "Upload_Id", "uploadId", "UploadId"),
        client=_first_present_in_sources(
            payload,
            fields,
            "Client",
            "client",
            "Nom_Client",
            "Assure",
            "Assuré",
            "Lese",
            "Lésé",
            "Informations Générales|Client",
            "custom_t2",
            "customT2",
        ),
        sinistre=_first_present_in_sources(
            payload,
            fields,
            "Sinistre",
            "sinistre",
            "Numero_Sinistre",
            "Numéro sinistre",
            "N° SINISTRE",
            "N_Sinistre",
            "Informations Générales| N° de sinistre",
            "custom_t5",
            "customT5",
        ),
        expert=_first_present_in_sources(
            payload,
            fields,
            "Expert",
            "expert",
            "Nom_Expert",
            "Code Expert",
            "Informations Générales| Nom de l'expert",
            "custom_t6",
            "customT6",
        ),
        immatriculation=_first_present_in_sources(
            payload,
            fields,
            "Immatriculation",
            "immatriculation",
            "Immat",
            "Registration",
            "Immat.",
            "Immatriculation véhicule",
            "Informations Générales|Immatriculation véhicule",
            "custom_t1",
            "customT1",
        ),
        date=_first_present_in_sources(
            payload,
            fields,
            "Date",
            "Date_Document",
            "dateDocument",
            "Informations Générales|Date du sinistre",
            "Informations Générales|Date visite expert",
            "custom_d4",
            "custom_d1",
            "customD4",
            "customD1",
        ),
        fields=fields,
        raw=payload,
    )


def _first_present_in_sources(
    payload: dict[str, Any],
    fields: dict[str, Any],
    *keys: str,
) -> Any:
    value = _first_present(payload, *keys)
    if value not in (None, ""):
        return _scalar_value(value)
    return _scalar_value(_first_present(fields, *keys))


def _extract_index_values(payload: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for container_name in ("indexes", "properties"):
        container = payload.get(container_name)
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    _add_index_value(values, item)
        elif isinstance(container, dict):
            values.update(container)
            for key, value in container.items():
                normalized = _normalize_custom_key(str(key))
                if normalized != key:
                    values[normalized] = value
    return values


def _add_index_value(values: dict[str, Any], item: dict[str, Any]) -> None:
    value = _first_present(item, "value", "Value", "val", "Val")
    if value in (None, ""):
        return
    for key_name in (
        "label",
        "Label",
        "customName",
        "CustomName",
        "index_Id",
        "Index_Id",
        "indexId",
        "IndexId",
        "columnName",
        "ColumnName",
        "id",
        "Id",
    ):
        key = item.get(key_name)
        if key not in (None, ""):
            key_text = str(key)
            values[key_text] = value
            values[_normalize_custom_key(key_text)] = value


def _normalize_custom_key(key: str) -> str:
    match = re.fullmatch(r"custom_([tdn])(\d+)", key, flags=re.IGNORECASE)
    if match:
        return f"custom{match.group(1).upper()}{match.group(2)}"
    match = re.fullmatch(r"custom([TDN])(\d+)", key)
    if match:
        return f"custom_{match.group(1).lower()}{match.group(2)}"
    return key


def _scalar_value(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1:
            return value[0]
    return value
