from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from .config import ZeendocSettings
from .pipeline import RepairOrderPipeline
from .zeendoc_client import ZeendocClient


DEFAULT_OUTPUT_DIR = Path(os.getenv("OR_EXTRACTOR_OUTPUT_DIR", "/tmp/or-extractor"))

app = FastAPI(
    title="Zeendoc OR Extractor",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("or_extractor.web_app:app", host="0.0.0.0", port=port)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _check_api_token(
    token: Annotated[str | None, Query(alias="token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("OR_EXTRACTOR_API_TOKEN")
    if not expected:
        return
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if token != expected and bearer != expected:
        raise HTTPException(status_code=401, detail="Token API invalide.")


@app.get("/generate-or", response_model=None)
def generate_or(
    res_id: Annotated[str, Query(description="ResId du PV Zeendoc a traiter.")],
    download: Annotated[bool, Query(description="Retourne le PDF directement si true.")] = False,
    upload_or: Annotated[bool | None, Query(description="Force l'upload de l'OR dans Zeendoc.")] = None,
    mark_processed: Annotated[bool | None, Query(description="Force le marquage du PV source.")] = None,
    _: None = Depends(_check_api_token),
) -> Any:
    res_id = _clean_zeendoc_id(res_id)
    settings = ZeendocSettings.from_env()
    output_dir = _output_dir()
    client = ZeendocClient(settings.base_url, settings.login, settings.password)
    client.authenticate()

    try:
        document = client.get_document(
            binder_id=settings.binder_id,
            res_id=res_id,
            wanted_columns=settings.wanted_columns,
            line_config_file_name=settings.line_config_file_name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Impossible de recuperer le document Zeendoc Res_Id={res_id}. "
                "Pour traiter une recherche, utilisez /process-search?search_id=24."
            ),
        ) from exc
    pipeline = RepairOrderPipeline(
        settings=settings,
        output_dir=output_dir,
        client=client,
        upload_or=_bool_env("OR_API_UPLOAD_OR", True) if upload_or is None else upload_or,
        mark_processed=_bool_env("OR_API_MARK_PROCESSED", False)
        if mark_processed is None
        else mark_processed,
    )
    result = pipeline.process_document(document)
    pipeline.write_report([result])

    if result.status == "error":
        raise HTTPException(status_code=500, detail=result.message)
    if result.status == "ignored":
        raise HTTPException(status_code=422, detail=result.message)
    if download and result.pdf_path:
        return FileResponse(
            result.pdf_path,
            media_type="application/pdf",
            filename=result.pdf_path.name,
        )

    return {
        "document_id": result.document_id,
        "status": result.status,
        "message": result.message,
        "line_count": result.line_count,
        "uploaded": result.uploaded,
        "marked_processed": result.marked_processed,
        "pdf": str(result.pdf_path) if result.pdf_path else None,
        "json": str(result.json_path) if result.json_path else None,
        "html": str(result.html_path) if result.html_path else None,
    }


@app.get("/process-search")
def process_search(
    search_id: Annotated[str | None, Query(description="Id de recherche Zeendoc a traiter.")] = None,
    limit: Annotated[int | None, Query(description="Limite de documents, utile pour tester.")] = None,
    upload_or: Annotated[bool | None, Query(description="Force l'upload des OR dans Zeendoc.")] = None,
    mark_processed: Annotated[bool | None, Query(description="Force le marquage des PV source.")] = None,
    _: None = Depends(_check_api_token),
) -> dict[str, object]:
    settings = ZeendocSettings.from_env()
    if search_id:
        settings = ZeendocSettings(
            base_url=settings.base_url,
            login=settings.login,
            password=settings.password,
            binder_id=settings.binder_id,
            wanted_columns=settings.wanted_columns,
            line_config_file_name=settings.line_config_file_name,
            search_id=_clean_zeendoc_id(search_id),
            or_source_id=settings.or_source_id,
            or_document_type_field=settings.or_document_type_field,
            or_document_type_value=settings.or_document_type_value,
            processed_field=settings.processed_field,
            processed_value=settings.processed_value,
        )
    pipeline = RepairOrderPipeline(
        settings=settings,
        output_dir=_output_dir(),
        upload_or=_bool_env("OR_API_UPLOAD_OR", True) if upload_or is None else upload_or,
        mark_processed=_bool_env("OR_API_MARK_PROCESSED", False)
        if mark_processed is None
        else mark_processed,
    )
    results = pipeline.run(limit=limit)
    return {
        "search_id": settings.search_id,
        "total": len(results),
        "generated": sum(result.status == "generated" for result in results),
        "uploaded": sum(result.uploaded for result in results),
        "marked_processed": sum(result.marked_processed for result in results),
        "ignored": sum(result.status == "ignored" for result in results),
        "errors": sum(result.status == "error" for result in results),
        "line_count": sum(result.line_count for result in results),
        "documents": [
            {
                "document_id": result.document_id,
                "status": result.status,
                "message": result.message,
                "line_count": result.line_count,
                "uploaded": result.uploaded,
                "marked_processed": result.marked_processed,
            }
            for result in results
        ],
    }


def _output_dir() -> Path:
    path = DEFAULT_OUTPUT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "oui"}


def _clean_zeendoc_id(value: str) -> str:
    return value.strip().strip("{}")
