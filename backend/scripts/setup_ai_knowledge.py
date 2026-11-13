"""Create an OpenAI vector store from only the two approved CourtBazaar sources.

The allowlist is deliberately explicit. Files outside it, including .env,
credentials, and arbitrary user documents, are never selected for upload.
"""
from pathlib import Path
import os

from dotenv import load_dotenv, set_key
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "ai_knowledge"
SOURCE_NAMES = (
    "DIAC Rules conclusive_UsingOCR.pdf",
    "STANDARD OPERATING PROCEDURE (SOP).docx",
)
SOURCES = tuple(KNOWLEDGE_DIR / name for name in SOURCE_NAMES)
SOURCE_ATTRIBUTES = {
    "DIAC Rules conclusive_UsingOCR.pdf": {
        "source_id": "diac_rules",
        "title": "DIAC Rules conclusive_UsingOCR.pdf",
    },
    "STANDARD OPERATING PROCEDURE (SOP).docx": {
        "source_id": "court_bazaar_sop",
        "title": "STANDARD OPERATING PROCEDURE (SOP).docx",
    },
}


def vector_store_files(client, vector_store_id):
    """Return indexed vector-store files by filename, including their metadata."""
    files = {}
    for item in client.vector_stores.files.list(vector_store_id=vector_store_id):
        uploaded_file = client.files.retrieve(item.id)
        if item.status != "completed":
            raise SystemExit(f"File Search indexing is not complete for {uploaded_file.filename}.")
        files[uploaded_file.filename] = item
    return files


def main():
    env_path = ROOT / ".env"
    load_dotenv(env_path)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required (backend only).")
    current_files = {p.name for p in KNOWLEDGE_DIR.iterdir() if p.is_file()}
    if current_files != set(SOURCE_NAMES):
        raise SystemExit("Knowledge folder must contain exactly the two approved source files.")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    vector_store_id = os.environ.get("OPENAI_VECTOR_STORE_ID", "").strip()
    if vector_store_id:
        client.vector_stores.retrieve(vector_store_id)
        existing = vector_store_files(client, vector_store_id)
        unexpected = set(existing) - set(SOURCE_NAMES)
        if unexpected:
            raise SystemExit("Configured vector store contains files outside the approved allowlist; no files were uploaded.")
        already_present = set(existing)
    else:
        store = client.vector_stores.create(name="CourtBazaar official knowledge base")
        vector_store_id = store.id
        already_present = set()

    for path in SOURCES:
        if path.name in already_present:
            item = existing[path.name]
            if getattr(item, "attributes", None) != SOURCE_ATTRIBUTES[path.name]:
                client.vector_stores.files.update(
                    vector_store_id=vector_store_id,
                    file_id=item.id,
                    attributes=SOURCE_ATTRIBUTES[path.name],
                )
            continue
        if not path.is_file():
            raise SystemExit(f"Approved source is missing: {path.name}")
        with path.open("rb") as source:
            vector_file = client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store_id,
                file=source,
                attributes=SOURCE_ATTRIBUTES[path.name],
                chunking_strategy={"type": "auto"},
            )
        if getattr(vector_file, "status", None) != "completed":
            raise SystemExit(f"File Search indexing did not complete for {path.name}.")

    actual = vector_store_files(client, vector_store_id)
    if len(actual) != len(SOURCE_NAMES) or set(actual) != set(SOURCE_NAMES):
        raise SystemExit("Vector store verification failed: it must contain exactly the two approved source files.")
    for name, item in actual.items():
        if getattr(item, "attributes", None) != SOURCE_ATTRIBUTES[name]:
            raise SystemExit(f"Vector store source metadata verification failed for {name}.")

    set_key(str(env_path), "OPENAI_VECTOR_STORE_ID", vector_store_id, quote_mode="never")
    os.environ["OPENAI_VECTOR_STORE_ID"] = vector_store_id
    print(f"OPENAI_VECTOR_STORE_ID={vector_store_id}")
    for name in SOURCE_NAMES:
        item = actual[name]
        print(
            f"VERIFIED={name} status={item.status} attributes={SOURCE_ATTRIBUTES[name]} "
            f"chunking_strategy={getattr(item, 'chunking_strategy', None)}"
        )


if __name__ == "__main__":
    main()
