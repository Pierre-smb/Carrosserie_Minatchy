from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import ZeendocSettings
from .pipeline import RepairOrderPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extraction des PV d'expertise Zeendoc et generation d'OR."
    )
    parser.add_argument("--base-url", help="URL de base API Zeendoc, ex: https://.../api/v4")
    parser.add_argument("--login", help="Login Zeendoc. Preferer ZEENDOC_LOGIN.")
    parser.add_argument("--password", help="Mot de passe Zeendoc. Preferer ZEENDOC_PASSWORD.")
    parser.add_argument("--binder-id", help="Identifiant du classeur/armoire Zeendoc.")
    parser.add_argument("--wanted-columns", help="Colonnes/indices Zeendoc separes par des virgules.")
    parser.add_argument("--line-config", help="Nom de configuration d'extraction de lignes Zeendoc.")
    parser.add_argument(
        "--search-id",
        default=None,
        help="Identifiant de la recherche Zeendoc enregistree. Defaut metier: 24.",
    )
    parser.add_argument("--query", help="Nom d'une recherche Zeendoc enregistree, si l'ID n'est pas utilise.")
    parser.add_argument("--limit", type=int, help="Nombre maximal de PV a traiter.")
    parser.add_argument("--output-dir", type=Path, default=Path("out"))
    parser.add_argument(
        "--upload-or",
        action="store_true",
        help="Envoie le PDF OR genere dans Zeendoc avec indexation liee au PV.",
    )
    parser.add_argument(
        "--or-source-id",
        type=int,
        help="sourceId Zeendoc a utiliser pour l'upload de l'OR, si necessaire.",
    )
    parser.add_argument(
        "--mark-processed",
        action="store_true",
        help="Met a jour le PV source apres traitement.",
    )
    parser.add_argument(
        "--mark-field",
        help="Champ Zeendoc a mettre a jour pour le marquage. Defaut: ZEENDOC_PROCESSED_FIELD ou custom_n1.",
    )
    parser.add_argument(
        "--mark-value",
        help="Valeur Zeendoc du marquage. Defaut: ZEENDOC_PROCESSED_VALUE ou 1.",
    )
    parser.add_argument(
        "--debug-document",
        help="ResId d'un document a inspecter sans generer d'OR.",
    )
    parser.add_argument(
        "--debug-wanted-columns",
        help="wantedColumns a tester avec --debug-document. Defaut: configuration courante.",
    )
    parser.add_argument(
        "--list-fields",
        action="store_true",
        help="Liste les champs de classement disponibles pour le classeur, puis s'arrete.",
    )
    parser.add_argument(
        "--list-fields-raw",
        action="store_true",
        help="Affiche le JSON brut des champs de classement, puis s'arrete.",
    )
    args = parser.parse_args()

    settings = _settings_from_args(args)
    if args.list_fields or args.list_fields_raw:
        from .zeendoc_client import ZeendocClient

        client = ZeendocClient(settings.base_url, settings.login, settings.password)
        client.authenticate()
        fields = client.list_binder_fields(settings.binder_id)
        if args.list_fields_raw:
            print(json.dumps(fields, ensure_ascii=False, indent=2))
            return 0
        for field in fields:
            identifier = _field_identifier(field)
            label = field.get("label") or field.get("Label") or ""
            field_type = field.get("type") or field.get("Type") or ""
            print(
                f"{identifier}\t{label}\ttype={field_type}\tkeys={','.join(field.keys())}"
        )
        return 0

    if args.debug_document:
        from .zeendoc_client import ZeendocClient

        client = ZeendocClient(settings.base_url, settings.login, settings.password)
        client.authenticate()
        wanted_columns = args.debug_wanted_columns or settings.wanted_columns
        document = client.get_document(
            binder_id=settings.binder_id,
            res_id=args.debug_document,
            wanted_columns=wanted_columns,
            line_config_file_name=settings.line_config_file_name,
        )
        debug_dir = args.output_dir / "debug-zeendoc"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"document_{args.debug_document}.json"
        debug_path.write_text(
            json.dumps(document.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Document: {args.debug_document}")
        print(f"wantedColumns: {wanted_columns}")
        print(f"raw: {debug_path}")
        print("properties:")
        _print_debug_items(document.payload.get("properties"))
        print("indexes:")
        _print_debug_items(document.payload.get("indexes"))
        print("mapped fields:")
        for key, value in document.index.fields.items():
            print(f"  {key}: {value}")
        return 0

    pipeline = RepairOrderPipeline(
        settings=settings,
        output_dir=args.output_dir,
        upload_or=args.upload_or,
        mark_processed=args.mark_processed,
    )
    results = pipeline.run(query=args.query, limit=args.limit)
    for result in results:
        if result.status in {"generated", "uploaded"}:
            actions = []
            if result.uploaded:
                actions.append("OR remonte dans Zeendoc")
            if result.marked_processed:
                actions.append("PV marque traite")
            suffix = f" ({', '.join(actions)})" if actions else ""
            print(
                f"[OK] {result.document_id}: {result.json_path} | "
                f"{result.html_path} | {result.pdf_path} | lignes={result.line_count}{suffix}"
            )
        else:
            print(f"[{result.status.upper()}] {result.document_id}: {result.message}")
    print(f"Rapport: {args.output_dir / 'report.json'}")
    return 0 if all(result.status != "error" for result in results) else 1


def _settings_from_args(args: argparse.Namespace) -> ZeendocSettings:
    if args.base_url:
        os.environ["ZEENDOC_BASE_URL"] = args.base_url
    if args.login:
        os.environ["ZEENDOC_LOGIN"] = args.login
    if args.password:
        os.environ["ZEENDOC_PASSWORD"] = args.password
    if args.binder_id:
        os.environ["ZEENDOC_BINDER_ID"] = args.binder_id
    if args.wanted_columns:
        os.environ["ZEENDOC_WANTED_COLUMNS"] = args.wanted_columns
    if args.line_config:
        os.environ["ZEENDOC_LINE_CONFIG"] = args.line_config
    if args.search_id:
        os.environ["ZEENDOC_SEARCH_ID"] = args.search_id
    if args.or_source_id is not None:
        os.environ["ZEENDOC_OR_SOURCE_ID"] = str(args.or_source_id)
    if args.mark_field:
        os.environ["ZEENDOC_PROCESSED_FIELD"] = args.mark_field
    if args.mark_value:
        os.environ["ZEENDOC_PROCESSED_VALUE"] = args.mark_value
    return ZeendocSettings.from_env()


def _field_identifier(field: dict[str, object]) -> str:
    for key in (
        "indexId",
        "IndexId",
        "index_Id",
        "Index_Id",
        "customName",
        "CustomName",
        "columnName",
        "ColumnName",
        "id",
        "Id",
        "label",
        "Label",
    ):
        value = field.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _print_debug_items(value: object) -> None:
    if isinstance(value, list):
        if not value:
            print("  []")
        for item in value:
            if isinstance(item, dict):
                label = item.get("label") or item.get("Label") or item.get("index_Id") or item.get("id")
                item_value = item.get("value") or item.get("Value")
                print(f"  {label}: {item_value} keys={','.join(item.keys())}")
            else:
                print(f"  {item}")
    elif isinstance(value, dict):
        if not value:
            print("  {}")
        for key, item_value in value.items():
            print(f"  {key}: {item_value}")
    else:
        print(f"  {value}")


if __name__ == "__main__":
    raise SystemExit(main())
