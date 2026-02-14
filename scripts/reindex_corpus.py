#!/usr/bin/env python3
"""
Re-index ChromaDB corpus embeddings with Jina v3 (retrieval.passage).

Features:
- Batch processing (default batch_size=64)
- tqdm progress bar with throughput and ETA
- Resume support via checkpoint file
- Dry-run mode (process 100 docs, no writes)
- CPU default, optional GPU mode
- Validation queries before/after re-indexing

Usage:
    python scripts/reindex_corpus.py --dry-run
    python scripts/reindex_corpus.py
    python scripts/reindex_corpus.py --device gpu
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Make backend package importable when run from repository root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

DEFAULT_VALIDATION_QUERIES = [
    "Vad säger arbetsmiljölagen om arbetsgivarens ansvar?",
    "Vilka regler gäller för uppsägning enligt LAS?",
    "Hur definieras diskriminering i diskrimineringslagen?",
    "Vad innebär offentlighetsprincipen enligt svensk rätt?",
    "Vilket ansvar har kommunen enligt socialtjänstlagen?",
]


def _log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_collections(
    client: chromadb.PersistentClient,
    target_suffix: str,
    source_suffix: str,
    explicit: str | None,
) -> list[tuple[str, str]]:
    if explicit:
        names = [item.strip() for item in explicit.split(",") if item.strip()]
        return [(name, name) for name in names]

    names = [c.name for c in client.list_collections() if not c.name.startswith("test_")]
    source_names = sorted(name for name in names if name.endswith(source_suffix))
    # If legacy/source collections exist (e.g. *_bge_m3_1024), prefer migrating from them
    # into target collections, even if some target collections already exist. This enables
    # safe resume for partial migrations without silently "re-indexing" the partial target.
    if source_names:
        return [
            (source_name, source_name[: -len(source_suffix)] + target_suffix)
            for source_name in source_names
        ]

    target_names = sorted(name for name in names if name.endswith(target_suffix))
    if target_names:
        # No source collections found; re-embed in-place for existing target collections.
        return [(name, name) for name in target_names]

    return []


@dataclass
class CollectionPair:
    source_name: str
    target_name: str


def _build_embedding_text(document: str, metadata: dict[str, Any] | None) -> str:
    metadata = metadata or {}
    title = str(metadata.get("title", "")).strip()
    page_content = str(metadata.get("page_content", "")).strip()
    doc = (document or "").strip()

    if title and doc:
        text = f"{title} {doc}"
    elif doc:
        text = doc
    elif page_content:
        text = f"{title} {page_content}".strip() if title else page_content
    else:
        text = title

    return text if text else " "


def _load_validation_queries(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_VALIDATION_QUERIES
    file_path = Path(path)
    if not file_path.exists():
        _log(f"Validation query file missing: {file_path}, using defaults")
        return DEFAULT_VALIDATION_QUERIES

    queries = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            queries.append(stripped)
    return queries if queries else DEFAULT_VALIDATION_QUERIES


def _release_cuda_cache_if_available() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()


def _run_validation(
    client: chromadb.PersistentClient,
    model: SentenceTransformer,
    collections: list[str],
    queries: list[str],
    top_k: int = 10,
) -> dict[str, int]:
    _log(f"Running validation with {len(queries)} queries (top_k={top_k})")
    results: dict[str, int] = {}

    for query in queries:
        query_embedding = model.encode(
            [query],
            task="retrieval.query",
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0].tolist()

        total = 0
        for collection_name in collections:
            try:
                collection = client.get_collection(name=collection_name)
            except Exception:
                continue
            response = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["distances"],
            )
            ids = response.get("ids", [[]])
            count = len(ids[0]) if ids and len(ids) > 0 else 0
            total += count

        results[query] = total
        _log(f"Validation: '{query[:60]}' -> {total} results")

    return results


def _print_validation_diff(before: dict[str, int], after: dict[str, int]) -> None:
    print("\nValidation diff (before -> after):")
    print("-" * 92)
    print(f"{'Query':60} | {'Before':>8} | {'After':>8} | {'Delta':>8}")
    print("-" * 92)
    for query, before_count in before.items():
        after_count = after.get(query, 0)
        delta = after_count - before_count
        print(f"{query[:60]:60} | {before_count:8d} | {after_count:8d} | {delta:8d}")
    print("-" * 92)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-index ChromaDB embeddings with Jina v3.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only 100 documents and do not write embeddings.",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "gpu"],
        default="cpu",
        help="Embedding device (default: cpu).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for embedding generation (default: 64).",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=str(REPO_ROOT / "migration_checkpoints" / "reindex_checkpoint.json"),
        help="Checkpoint JSON file path.",
    )
    parser.add_argument(
        "--collections",
        default=None,
        help="Comma-separated collection names to process. Default: auto-detect *_jina_v3_1024.",
    )
    parser.add_argument(
        "--validation-queries-file",
        default=None,
        help="Optional file with one validation query per line.",
    )
    parser.add_argument(
        "--source-suffix",
        default="_bge_m3_1024",
        help="Source collection suffix for migration (default: _bge_m3_1024).",
    )
    return parser.parse_args()


def main() -> None:
    from app.services.config_service import get_config_service

    args = _parse_args()
    start_time = time.perf_counter()
    dry_run_limit = 100

    config = get_config_service()
    chroma_path = Path(config.chromadb_path)
    checkpoint_path = Path(args.checkpoint_file)

    _log("Starting corpus re-indexing")
    _log(f"ChromaDB path: {chroma_path}")
    _log(f"Embedding model: {config.embedding_model}")
    _log(f"Batch size: {args.batch_size}")
    _log(f"Dry run: {args.dry_run}")

    device = args.device
    if device == "gpu":
        import torch

        if not torch.cuda.is_available():
            _log("GPU requested but CUDA is not available. Falling back to CPU.")
            device = "cpu"
        else:
            _log(
                "GPU mode selected. Ensure llama-server is stopped first to free VRAM "
                "before full re-indexing."
            )

    sentence_device = "cuda" if device == "gpu" else "cpu"
    client = chromadb.PersistentClient(path=str(chroma_path))
    resolved = _resolve_collections(
        client=client,
        target_suffix=config.settings.embedding_collection_suffix,
        source_suffix=args.source_suffix,
        explicit=args.collections,
    )

    if not resolved:
        _log("No matching collections found. Exiting.")
        sys.exit(1)

    pairs: list[CollectionPair] = [
        CollectionPair(source_name=source, target_name=target) for source, target in resolved
    ]
    _log(
        f"Collections to process ({len(pairs)}): "
        f"{[(pair.source_name, pair.target_name) for pair in pairs]}"
    )
    validation_queries = _load_validation_queries(args.validation_queries_file)

    # Load checkpoint only for writable runs.
    checkpoint = _load_checkpoint(checkpoint_path) if not args.dry_run else {}
    offsets = checkpoint.get("collection_offsets", {}) if isinstance(checkpoint, dict) else {}
    last_ids = checkpoint.get("last_processed_id", {}) if isinstance(checkpoint, dict) else {}
    checkpoint_errors = checkpoint.get("errors", []) if isinstance(checkpoint, dict) else []
    error_count = int(checkpoint.get("error_count", 0)) if isinstance(checkpoint, dict) else 0
    # Keep a stable run start timestamp; older versions re-wrote started_at repeatedly.
    run_started_at = checkpoint.get("started_at") or time.strftime("%Y-%m-%d %H:%M:%S")

    if checkpoint and not args.dry_run:
        _log(f"Loaded checkpoint from: {checkpoint_path}")
        _log(f"Resume offsets: {offsets}")

    # Load embedding model.
    _log(f"Loading embedding model on {sentence_device}...")
    try:
        model = SentenceTransformer(
            config.embedding_model,
            device=sentence_device,
            trust_remote_code=True,
        )
    except TypeError:
        model = SentenceTransformer(config.embedding_model, device=sentence_device)
    _log("Embedding model loaded.")

    target_collections = [pair.target_name for pair in pairs]

    if not args.dry_run:
        for pair in pairs:
            target_exists = False
            try:
                client.get_collection(name=pair.target_name)
                target_exists = True
            except Exception:
                target_exists = False

            if not target_exists:
                source = client.get_collection(name=pair.source_name)
                metadata = source.metadata if source.metadata else {}
                client.get_or_create_collection(name=pair.target_name, metadata=metadata)
                _log(f"Created target collection: {pair.target_name} (from {pair.source_name})")

    # Validation before re-indexing.
    validation_before = _run_validation(client, model, target_collections, validation_queries)

    # Compute total document target.
    counts_by_collection: dict[str, int] = {}
    for pair in pairs:
        counts_by_collection[pair.target_name] = client.get_collection(
            name=pair.source_name
        ).count()

    remaining_total = 0
    for pair in pairs:
        name = pair.target_name
        offset = int(offsets.get(name, 0)) if not args.dry_run else 0
        remaining_total += max(0, counts_by_collection[name] - offset)

    target_docs = min(remaining_total, dry_run_limit) if args.dry_run else remaining_total
    _log(f"Documents remaining to process: {remaining_total}")
    _log(f"Target documents this run: {target_docs}")

    processed = 0
    written = 0
    overall_start = time.perf_counter()
    batches_since_cache_release = 0

    with tqdm(total=target_docs, desc="Re-indexing", unit="docs") as pbar:
        for pair in pairs:
            source_collection = client.get_collection(name=pair.source_name)
            target_collection = (
                client.get_collection(name=pair.target_name) if not args.dry_run else None
            )
            collection_name = pair.target_name
            total_docs = counts_by_collection[collection_name]
            offset = 0 if args.dry_run else int(offsets.get(collection_name, 0))
            current_batch_size = max(1, int(args.batch_size))
            # When CUDA OOM happens, clamp future "recovery" so we don't bounce back to an
            # unsafe batch size and thrash VRAM.
            allowed_max_batch_size = current_batch_size

            if offset >= total_docs:
                _log(f"{collection_name}: already complete ({offset}/{total_docs})")
                continue

            _log(f"{collection_name}: processing from offset {offset} of {total_docs}")

            while offset < total_docs:
                if processed >= target_docs:
                    break

                remaining_global = target_docs - processed
                remaining_collection = total_docs - offset
                batch_limit = min(current_batch_size, remaining_global, remaining_collection)

                batch = source_collection.get(
                    limit=batch_limit,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                ids = batch.get("ids", [])
                documents = batch.get("documents", [])
                metadatas = batch.get("metadatas", [])

                if not ids:
                    break

                try:
                    texts = [
                        _build_embedding_text(
                            document=documents[idx] if idx < len(documents) else "",
                            metadata=metadatas[idx] if idx < len(metadatas) else {},
                        )
                        for idx in range(len(ids))
                    ]

                    embeddings = model.encode(
                        texts,
                        task="retrieval.passage",
                        convert_to_numpy=True,
                        show_progress_bar=False,
                    ).tolist()

                    if not args.dry_run and target_collection is not None:
                        target_collection.upsert(
                            ids=ids,
                            documents=documents,
                            metadatas=metadatas,
                            embeddings=embeddings,
                        )
                        written += len(ids)

                    processed += len(ids)
                    offset += len(ids)
                    pbar.update(len(ids))

                    # After adaptive retry on failures, gradually recover batch size.
                    if current_batch_size < allowed_max_batch_size:
                        current_batch_size = min(allowed_max_batch_size, current_batch_size * 2)

                    elapsed = max(0.001, time.perf_counter() - overall_start)
                    docs_per_sec = processed / elapsed
                    remaining = max(0, target_docs - processed)
                    eta_seconds = remaining / docs_per_sec if docs_per_sec > 0 else 0.0
                    pbar.set_postfix(
                        {
                            "docs/s": f"{docs_per_sec:.2f}",
                            "eta": _format_duration(eta_seconds),
                            "errors": error_count,
                        }
                    )

                    if not args.dry_run:
                        offsets[collection_name] = offset
                        last_ids[collection_name] = ids[-1]
                        checkpoint_payload = {
                            "started_at": run_started_at,
                            "device": device,
                            "batch_size": args.batch_size,
                            "collection_offsets": offsets,
                            "last_processed_id": last_ids,
                            "processed_total": processed,
                            "written_total": written,
                            "error_count": error_count,
                            "errors": checkpoint_errors[-20:],
                            "completed": False,
                        }
                        _save_checkpoint(checkpoint_path, checkpoint_payload)

                    # Periodically release CUDA cache to reduce fragmentation and avoid
                    # "almost full VRAM" states that make small allocations fail.
                    if device == "gpu":
                        batches_since_cache_release += 1
                        if batches_since_cache_release >= 50:
                            _release_cuda_cache_if_available()
                            batches_since_cache_release = 0

                except Exception as exc:
                    err_lower = str(exc).lower()
                    is_cuda_oom = ("out of memory" in err_lower) or (
                        ("cuda" in err_lower) and ("memory" in err_lower)
                    )
                    # Retry the same offset with smaller batches to avoid data gaps.
                    if len(ids) > 1:
                        next_batch_size = max(1, len(ids) // 2)
                        if next_batch_size < current_batch_size:
                            current_batch_size = next_batch_size
                        if is_cuda_oom:
                            allowed_max_batch_size = min(allowed_max_batch_size, current_batch_size)
                        _log(
                            f"WARN: {collection_name} offset={offset} batch_size={len(ids)} "
                            f"failed ({exc!s}). Retrying with batch_size={current_batch_size}."
                        )
                        _release_cuda_cache_if_available()
                        batches_since_cache_release = 0
                        continue

                    # Hard failure on a single document: skip exactly one doc and continue.
                    error_count += 1
                    error_msg = (
                        f"{collection_name} offset={offset} batch_size={len(ids)} error={exc!s}"
                    )
                    checkpoint_errors.append(error_msg)
                    _log(f"ERROR: {error_msg}")
                    offset += 1
                    processed += 1
                    pbar.update(1)
                    _release_cuda_cache_if_available()
                    batches_since_cache_release = 0

                    if not args.dry_run:
                        offsets[collection_name] = offset
                        if ids:
                            last_ids[collection_name] = ids[-1]
                        checkpoint_payload = {
                            "started_at": run_started_at,
                            "device": device,
                            "batch_size": args.batch_size,
                            "collection_offsets": offsets,
                            "last_processed_id": last_ids,
                            "processed_total": processed,
                            "written_total": written,
                            "error_count": error_count,
                            "errors": checkpoint_errors[-20:],
                            "completed": False,
                        }
                        _save_checkpoint(checkpoint_path, checkpoint_payload)

            if processed >= target_docs:
                break

    # Validation after run.
    validation_after = _run_validation(client, model, target_collections, validation_queries)
    _print_validation_diff(validation_before, validation_after)

    elapsed_total = time.perf_counter() - start_time
    docs_per_sec_total = processed / elapsed_total if elapsed_total > 0 else 0.0

    _log("Re-indexing finished")
    _log(f"Processed documents: {processed}")
    _log(f"Written embeddings: {written} {'(dry-run: no writes)' if args.dry_run else ''}")
    _log(f"Errors: {error_count}")
    _log(f"Total time: {_format_duration(elapsed_total)} ({elapsed_total:.1f}s)")
    _log(f"Throughput: {docs_per_sec_total:.2f} docs/sec")

    if not args.dry_run:
        final_checkpoint = {
            "started_at": run_started_at,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "device": device,
            "batch_size": args.batch_size,
            "collection_offsets": offsets,
            "last_processed_id": last_ids,
            "processed_total": processed,
            "written_total": written,
            "error_count": error_count,
            "errors": checkpoint_errors[-20:],
            "completed": True,
        }
        _save_checkpoint(checkpoint_path, final_checkpoint)
        _log(f"Checkpoint updated: {checkpoint_path}")


if __name__ == "__main__":
    main()
