"""Create or top up the OpenAI vector store from only the approved sources.

The allowlist comes from kb_registry (kb/arbitration_kb_metadata.json + SOP).
Files outside it, including .env, credentials, and arbitrary user documents,
are never selected for upload. Only files missing from the store are uploaded;
nothing is ever deleted from it. `--dry-run` only prints what it would do.
"""
from pathlib import Path
import argparse
import os
import sys

from dotenv import load_dotenv, set_key
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "ai_knowledge"
sys.path.insert(0, str(ROOT))
import kb_registry  # noqa: E402

SOURCE_NAMES = tuple(sorted(kb_registry.approved_files()))
SOURCES = tuple(KNOWLEDGE_DIR / name for name in SOURCE_NAMES)
SOURCE_ATTRIBUTES = {name: kb_registry.vector_store_attributes(name) for name in SOURCE_NAMES}


def vector_store_files(client, vector_store_id):
    """Return indexed vector-store files by filename, including their metadata.
    A filename stored twice is refused: it would hide one copy from every check."""
    files = {}
    for item in client.vector_stores.files.list(vector_store_id=vector_store_id):
        uploaded_file = client.files.retrieve(item.id)
        if item.status != "completed":
            raise SystemExit(f"File Search indexing is not complete for {uploaded_file.filename}.")
        if uploaded_file.filename in files:
            raise SystemExit(f"Vector store holds {uploaded_file.filename} more than once; delete the extra copy.")
        files[uploaded_file.filename] = item
    return files


def stale_attributes(existing, expected):
    """Store files (by name) whose attributes differ in any way from the registry's."""
    return sorted(name for name, item in existing.items()
                  if name in expected and dict(getattr(item, "attributes", None) or {}) != expected[name])


def unknown_store_files(existing, names):
    """Store files the registry doesn't list (to be deleted by hand)."""
    return sorted(set(existing) - set(names))


def update_attributes(client, vector_store_id, existing, expected):
    for name in stale_attributes(existing, expected):
        client.vector_stores.files.update(
            vector_store_id=vector_store_id, file_id=existing[name].id, attributes=expected[name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would be uploaded, change nothing")
    dry_run = parser.parse_args().dry_run
    if kb_registry.load_error():
        # An empty registry would report every store file as "not in registry" and upload nothing useful.
        raise SystemExit(f"KB metadata failed to load, fix it first: {kb_registry.load_error()}")
    env_path = ROOT / ".env"
    load_dotenv(env_path)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required (backend only).")
    current_files = {p.name for p in KNOWLEDGE_DIR.iterdir() if p.is_file()}
    if current_files != set(SOURCE_NAMES):
        raise SystemExit("Knowledge folder must contain exactly the approved source files.")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    vector_store_id = os.environ.get("OPENAI_VECTOR_STORE_ID", "").strip()
    if vector_store_id:
        client.vector_stores.retrieve(vector_store_id)
        existing = vector_store_files(client, vector_store_id)
        unexpected = unknown_store_files(existing, SOURCE_NAMES)
        for name in unexpected:
            print(f"NOT IN REGISTRY (delete by hand): {name}")
        if unexpected and not dry_run:
            raise SystemExit("Configured vector store contains files outside the approved allowlist; no files were uploaded.")
        already_present = set(existing)
    elif dry_run:
        existing, already_present = {}, set()
        vector_store_id = "<new store>"
    else:
        store = client.vector_stores.create(name="CourtBazaar official knowledge base")
        vector_store_id = store.id
        existing, already_present = {}, set()

    for name in stale_attributes(existing, SOURCE_ATTRIBUTES):
        print(f"{'WOULD UPDATE' if dry_run else 'UPDATING'} ATTRIBUTES {name} -> {SOURCE_ATTRIBUTES[name]}")
    if not dry_run:
        update_attributes(client, vector_store_id, existing, SOURCE_ATTRIBUTES)

    for path in SOURCES:
        if path.name in already_present:
            continue
        if not path.is_file():
            raise SystemExit(f"Approved source is missing: {path.name}")
        if dry_run:
            print(f"WOULD UPLOAD {path.name} attributes={SOURCE_ATTRIBUTES[path.name]}")
            continue
        with path.open("rb") as source:
            vector_file = client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store_id,
                file=source,
                attributes=SOURCE_ATTRIBUTES[path.name],
                chunking_strategy={"type": "auto"},
            )
        if getattr(vector_file, "status", None) != "completed":
            raise SystemExit(f"File Search indexing did not complete for {path.name}.")

    if dry_run:
        print(f"Dry run against {vector_store_id}: nothing changed.")
        return

    # Unique file names, not records: one PDF can carry several records (DIAC, ICC).
    actual = vector_store_files(client, vector_store_id)
    if set(actual) != set(SOURCE_NAMES):
        raise SystemExit("Vector store verification failed: it must contain exactly the approved source files.")
    if stale_attributes(actual, SOURCE_ATTRIBUTES):
        # Any difference left (a file uploaded earlier, a status change): update once more, then re-verify.
        update_attributes(client, vector_store_id, actual, SOURCE_ATTRIBUTES)
        actual = vector_store_files(client, vector_store_id)
    for name in stale_attributes(actual, SOURCE_ATTRIBUTES):
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
