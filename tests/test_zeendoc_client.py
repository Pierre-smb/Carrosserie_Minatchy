from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from or_extractor.zeendoc_client import ZeendocClient


@dataclass
class FakeResponse:
    payload: dict[str, Any]
    status_code: int = 200
    text: str = ""

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.patches: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], timeout: int) -> FakeResponse:
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"nbDocs": 0, "document": []})

    def patch(self, url: str, json: dict[str, Any], timeout: int) -> FakeResponse:
        self.patches.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"updated": True}, text='{"updated": true}')


def test_search_uses_saved_query_id():
    session = FakeSession()
    client = ZeendocClient(
        base_url="https://zeendoc.example/api/v4",
        login="login",
        password="password",
        session=session,  # type: ignore[arg-type]
    )

    list(
        client.iter_documents(
            binder_id="coll_1",
            wanted_columns="Res_Id,Client",
            search_id="24",
        )
    )

    assert session.posts[0]["url"] == "https://zeendoc.example/api/v4/binders/coll_1/documents/search"
    assert session.posts[0]["json"]["savedQueryId"] == 24
    assert session.posts[0]["json"]["wantedColumns"] == "Res_Id,Client"


def test_upload_document_sends_indexation(tmp_path):
    session = FakeSession()
    client = ZeendocClient(
        base_url="https://zeendoc.example/api/v4",
        login="login",
        password="password",
        session=session,  # type: ignore[arg-type]
    )
    pdf_path = tmp_path / "or_39.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    client.upload_document(
        binder_id="coll_1",
        file_path=pdf_path,
        source_id=12,
        indexation={"custom_t2": "VIRAMA MAYA", "custom_n3": "18"},
    )

    payload = session.posts[0]["json"]
    assert session.posts[0]["url"] == "https://zeendoc.example/api/v4/binders/coll_1/documents"
    assert payload["fileName"] == "or_39.pdf"
    assert payload["sourceId"] == 12
    assert payload["indexation"] == {"custom_t2": "VIRAMA MAYA", "custom_n3": "18"}


def test_update_document_indexes_uses_patch_index_list():
    session = FakeSession()
    client = ZeendocClient(
        base_url="https://zeendoc.example/api/v4",
        login="login",
        password="password",
        session=session,  # type: ignore[arg-type]
    )

    client.update_document_indexes(
        binder_id="coll_1",
        res_id="39",
        indexes={"custom_n1": "1", "empty": ""},
    )

    assert session.patches[0]["url"] == "https://zeendoc.example/api/v4/binders/coll_1/documents/39/indexes"
    assert session.patches[0]["json"] == {
        "indexList": [{"label": "custom_n1", "value": "1"}]
    }
