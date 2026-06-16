from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ZeendocSettings
from .models import DocumentIndex, ExtractedTextFields, RepairOrder
from .or_generator import write_repair_order_html, write_repair_order_json
from .or_pdf_generator import write_repair_order_pdf
from .pv_parser import PvListNotFound, extract_text_fields, parse_expert_report_pages
from .text_cleaner import clean_ocr_text
from .zeendoc_client import ZeendocClient, ZeendocDocument


@dataclass(frozen=True)
class ProcessResult:
    document_id: str
    json_path: Path | None
    html_path: Path | None
    pdf_path: Path | None
    status: str
    message: str = ""
    line_count: int = 0
    uploaded: bool = False
    upload_response: dict[str, Any] | None = None
    marked_processed: bool = False
    mark_response: dict[str, Any] | None = None


class RepairOrderPipeline:
    def __init__(
        self,
        settings: ZeendocSettings,
        output_dir: Path,
        client: ZeendocClient | None = None,
        upload_or: bool = False,
        mark_processed: bool = False,
    ) -> None:
        self.settings = settings
        self.output_dir = output_dir
        self.upload_or = upload_or
        self.mark_processed = mark_processed
        self.client = client or ZeendocClient(
            base_url=settings.base_url,
            login=settings.login,
            password=settings.password,
        )

    def run(self, query: str | None = None, limit: int | None = None) -> list[ProcessResult]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client.authenticate()
        results: list[ProcessResult] = []
        for document in self.client.iter_documents(
            binder_id=self.settings.binder_id,
            wanted_columns=self.settings.wanted_columns,
            query=query,
            limit=limit,
            line_config_file_name=self.settings.line_config_file_name,
            search_id=self.settings.search_id,
        ):
            try:
                results.append(self.process_document(document))
            except Exception as exc:
                document_id = document.index.res_id or document.index.upload_id or "document"
                results.append(ProcessResult(document_id, None, None, None, "error", str(exc)))
        self.write_report(results)
        return results

    def process_document(self, document: ZeendocDocument) -> ProcessResult:
        document_id = document.index.res_id or document.index.upload_id or "document"
        try:
            raw_text = self.client.get_document_text(document)
            text_dir = self.output_dir / "source-text"
            text_dir.mkdir(parents=True, exist_ok=True)
            raw_text_path = text_dir / f"ocr_{_safe_file_id(document_id)}_raw.txt"
            text_path = text_dir / f"ocr_{_safe_file_id(document_id)}.txt"
            raw_text_path.write_text(raw_text, encoding="utf-8")
            text = clean_ocr_text(raw_text)
            text_path.write_text(text, encoding="utf-8")
            pages = [text]
            extracted = parse_expert_report_pages(pages)
            text_fields = extract_text_fields(text, extracted)
        except PvListNotFound as exc:
            return ProcessResult(document_id, None, None, None, "ignored", str(exc))
        except Exception as exc:
            return ProcessResult(document_id, None, None, None, "error", str(exc))

        document_index = _with_extracted_text_fields(document.index, text_fields)
        order = RepairOrder(document=document_index, extracted_list=extracted)
        json_path = self.output_dir / f"or_{_safe_file_id(document_id)}.json"
        html_path = self.output_dir / f"or_{_safe_file_id(document_id)}.html"
        pdf_path = self.output_dir / f"or_{_safe_file_id(document_id)}.pdf"
        write_repair_order_json(order, json_path)
        write_repair_order_html(order, html_path)
        write_repair_order_pdf(order, pdf_path)

        upload_response: dict[str, Any] | None = None
        marked_processed = False
        mark_response: dict[str, Any] | None = None
        status = "generated"
        message = ""

        if self.upload_or:
            upload_response = self.client.upload_document(
                binder_id=self.settings.binder_id,
                file_path=pdf_path,
                source_id=self.settings.or_source_id,
                indexation=self._build_or_indexation(document_index),
            )
            status = "uploaded"

        if self.mark_processed:
            if not document.index.res_id:
                raise ValueError("Impossible de marquer le PV comme traite: resId manquant.")
            mark_response = self.client.update_document_indexes(
                binder_id=self.settings.binder_id,
                res_id=document.index.res_id,
                indexes={
                    self.settings.processed_field: self.settings.processed_value,
                },
            )
            marked_processed = True
            message = (
                f"PV marque {self.settings.processed_field}="
                f"{self.settings.processed_value}"
            )

        return ProcessResult(
            document_id=document_id,
            json_path=json_path,
            html_path=html_path,
            pdf_path=pdf_path,
            status=status,
            message=message,
            line_count=len(extracted.lines),
            uploaded=upload_response is not None,
            upload_response=upload_response,
            marked_processed=marked_processed,
            mark_response=mark_response,
        )

    def write_report(self, results: list[ProcessResult]) -> Path:
        report_path = self.output_dir / "report.json"
        payload = {
            "summary": {
                "total": len(results),
                "generated": sum(result.status == "generated" for result in results),
                "uploaded": sum(result.uploaded for result in results),
                "marked_processed": sum(result.marked_processed for result in results),
                "ignored": sum(result.status == "ignored" for result in results),
                "errors": sum(result.status == "error" for result in results),
                "line_count": sum(result.line_count for result in results),
            },
            "documents": [self._result_to_report_item(result) for result in results],
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return report_path

    def _build_or_indexation(self, document: DocumentIndex) -> dict[str, Any]:
        copied_fields = (
            "custom_t2",
            "custom_t3",
            "custom_t4",
            "custom_t5",
            "custom_d4",
            "custom_d1",
            "custom_t6",
            "custom_t8",
            "custom_t1",
            "custom_t7",
            "custom_t9",
            "custom_t10",
            "custom_t11",
            "custom_t12",
        )
        indexation: dict[str, Any] = {}
        for field in copied_fields:
            value = _field_value(document, field, preserve_list=field == "custom_t10")
            if value not in (None, ""):
                indexation[field] = value
        indexation[self.settings.or_document_type_field] = self.settings.or_document_type_value
        if "custom_t3" not in indexation and document.res_id:
            indexation["custom_t3"] = f"OR-PV-{document.res_id}"
        return indexation

    @staticmethod
    def _result_to_report_item(result: ProcessResult) -> dict[str, Any]:
        return {
            "document_id": result.document_id,
            "status": result.status,
            "message": result.message,
            "line_count": result.line_count,
            "json_path": str(result.json_path) if result.json_path else None,
            "html_path": str(result.html_path) if result.html_path else None,
            "pdf_path": str(result.pdf_path) if result.pdf_path else None,
            "uploaded": result.uploaded,
            "marked_processed": result.marked_processed,
            "upload_response": result.upload_response,
            "mark_response": result.mark_response,
        }


def _with_extracted_text_fields(index: DocumentIndex, text_fields: ExtractedTextFields) -> DocumentIndex:
    fields = dict(index.fields)
    if text_fields.indexed_items:
        fields["custom_t10"] = text_fields.indexed_items
        fields["customT10"] = text_fields.indexed_items
    if text_fields.work_designation:
        fields["custom_t11"] = text_fields.work_designation
        fields["customT11"] = text_fields.work_designation
    if text_fields.observations:
        fields["custom_t12"] = text_fields.observations
        fields["customT12"] = text_fields.observations

    return DocumentIndex(
        res_id=index.res_id,
        upload_id=index.upload_id,
        client=index.client,
        sinistre=index.sinistre,
        expert=index.expert,
        immatriculation=index.immatriculation,
        date=index.date,
        fields=fields,
        raw=index.raw,
    )


def _field_value(document: DocumentIndex, field: str, preserve_list: bool = False) -> Any:
    candidates = (field, _alternate_custom_key(field))
    for key in candidates:
        value = document.fields.get(key)
        if value not in (None, ""):
            if preserve_list:
                return value
            return _scalar_value(value)
    return None


def _alternate_custom_key(field: str) -> str:
    parts = field.split("_")
    if len(parts) == 2 and parts[0] == "custom" and parts[1]:
        return f"custom{parts[1][0].upper()}{parts[1][1:]}"
    return field


def _scalar_value(value: Any) -> Any:
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1:
            return value[0]
    return value


def _safe_file_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
