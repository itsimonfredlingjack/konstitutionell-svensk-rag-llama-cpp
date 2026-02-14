#!/usr/bin/env python3
"""
Chroma Integrity Gate (Post-Vacuum)

Fail-closed integrity checks for Chroma persistent storage stability.

Primary goal:
- Detect intermittent HNSW/compactor/backfill failures (e.g. "Error loading hnsw index")
  BEFORE we restart backend/LLM or run benchmarks.

This script is intentionally deterministic and audit-friendly:
- Clear console output
- Optional append-only log file (--log)
- Structured JSON report (--output-json)

Exit codes:
0 = PASS
1 = FAIL (integrity gate failed; do not start services)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import chromadb

DEFAULT_COLLECTIONS = [
    "swedish_gov_docs_jina_v3_1024",
    "diva_research_jina_v3_1024",
]

DEFAULT_TEST_QUERIES = [
    "Vad säger arbetsmiljölagen om arbetsgivarens ansvar?",
    "Vilka regler gäller för uppsägning enligt LAS?",
    "Hur definieras diskriminering i diskrimineringslagen?",
]

# Substrings that strongly indicate the known intermittent failure mode.
HNSW_ERROR_PATTERNS = [
    "error sending backfill request to compactor",
    "error loading hnsw index",
    "hnsw segment reader",
    "compactor",
    "backfill",
]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _sleep_seconds(ms: int) -> float:
    return max(0.0, float(ms) / 1000.0)


def _contains_hnsw_compactor_hint(message: str) -> bool:
    msg = (message or "").lower()
    return any(pat in msg for pat in HNSW_ERROR_PATTERNS)


def _parse_collections(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed integrity checks for ChromaDB post-vacuum stability."
    )
    parser.add_argument("--path", default="chromadb_data", help="Chroma persistent directory path.")

    # Required by the prompt (names may differ in older scripts; keep aliases).
    parser.add_argument(
        "--collections",
        default=",".join(DEFAULT_COLLECTIONS),
        help="Comma-separated collection names to check (default: known flaky Jina collections).",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=10,
        help="Number of sequential query loops per collection (default: 10).",
    )
    parser.add_argument(
        "--n-results",
        type=int,
        default=5,
        help="n_results for query() (default: 5).",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Optional append-only log file path for audit logs.",
    )

    # Backwards-compatible aliases (existing runners might use these names).
    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Alias for --loops (kept for backwards compatibility).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Alias for --n-results (kept for backwards compatibility).",
    )
    parser.add_argument("--sleep-ms", type=int, default=200, help="Sleep between loops (ms).")

    parser.add_argument(
        "--output-json",
        default="logs/chroma_integrity_report.json",
        help="Write structured report JSON to this path (default: logs/chroma_integrity_report.json).",
    )
    return parser.parse_args()


def _emit(line: str, log_path: Path | None) -> None:
    print(line, flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _load_expected_dim() -> int:
    """
    Load expected embedding dimension from backend config, without loading models.

    This avoids pulling in sentence-transformers and large HF models during the gate.
    """
    repo_root = Path(__file__).resolve().parent.parent
    os.sys.path.insert(0, str(repo_root / "backend"))
    from app.services.config_service import get_config_service

    config = get_config_service()
    dim = int(getattr(config.settings, "expected_embedding_dim", 1024))
    return max(1, dim)


def _build_probe_embeddings(dim: int, queries: list[str]) -> list[list[float]]:
    """
    Deterministic, lightweight embeddings (no ML model).

    We only need valid-dimension float vectors to trigger HNSW reads. These are
    stable across runs and cheap to compute.
    """
    out: list[list[float]] = []
    for q in queries:
        # Seed from query text for reproducibility.
        seed = 0
        for ch in q[:128]:
            seed = (seed * 131 + ord(ch)) % (2**32)
        rng = random.Random(seed)
        vec = [float(rng.random() * 0.01) for _ in range(dim)]
        out.append(vec)
    return out


@dataclass
class LoopResult:
    loop_index: int
    query_index: int
    ok: bool
    ids_count: int
    latency_ms: float
    error: str | None = None
    error_hnsw_hint: bool = False


@dataclass
class CollectionReport:
    name: str
    count: int | None = None
    count_latency_ms: float = 0.0
    ok: bool = True
    loops: list[LoopResult] = field(default_factory=list)
    last_error: str | None = None


def _query_once(
    collection: Any,
    *,
    embedding: list[float],
    n_results: int,
) -> tuple[int, dict[str, Any]]:
    resp = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["distances"],
    )
    ids = resp.get("ids")
    if not ids or not isinstance(ids, list) or not ids[0]:
        return 0, resp
    return len(ids[0]), resp


def _check_collection(
    client: chromadb.PersistentClient,
    *,
    name: str,
    loops: int,
    n_results: int,
    sleep_s: float,
    probe_embeddings: list[list[float]],
    log_path: Path | None,
) -> CollectionReport:
    report = CollectionReport(name=name)

    _emit(f"[{_now_iso()}] collection={name} step=open", log_path)
    collection = client.get_collection(name=name)

    # count() once up front (required by spec)
    _emit(f"[{_now_iso()}] collection={name} step=count_start", log_path)
    t0 = time.perf_counter()
    try:
        report.count = int(collection.count())
        report.count_latency_ms = (time.perf_counter() - t0) * 1000.0
        _emit(
            f"[{_now_iso()}] collection={name} step=count_ok count={report.count} "
            f"latency_ms={report.count_latency_ms:.1f}",
            log_path,
        )
    except Exception as e:
        report.ok = False
        report.last_error = str(e)
        _emit(
            f"[{_now_iso()}] collection={name} step=count_FAIL error={type(e).__name__}: {e}",
            log_path,
        )
        return report

    # N sequential queries (fail-closed on any error)
    loops = max(1, int(loops))
    for i in range(loops):
        emb_idx = i % max(1, len(probe_embeddings))
        embedding = probe_embeddings[emb_idx]
        _emit(
            f"[{_now_iso()}] collection={name} step=query_start loop={i + 1}/{loops} probe={emb_idx + 1}",
            log_path,
        )
        t1 = time.perf_counter()
        try:
            ids_count, _ = _query_once(
                collection,
                embedding=embedding,
                n_results=n_results,
            )
            latency_ms = (time.perf_counter() - t1) * 1000.0

            # Unexpected empty: collection has docs but query returns nothing.
            if (report.count or 0) > 0 and ids_count == 0:
                raise RuntimeError("unexpected empty query result (count>0 but ids empty)")

            report.loops.append(
                LoopResult(
                    loop_index=i + 1,
                    query_index=emb_idx + 1,
                    ok=True,
                    ids_count=ids_count,
                    latency_ms=latency_ms,
                )
            )
            _emit(
                f"[{_now_iso()}] collection={name} step=query_ok loop={i + 1}/{loops} "
                f"ids_count={ids_count} latency_ms={latency_ms:.1f}",
                log_path,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t1) * 1000.0
            msg = str(e)
            hint = _contains_hnsw_compactor_hint(msg)
            report.ok = False
            report.last_error = msg
            report.loops.append(
                LoopResult(
                    loop_index=i + 1,
                    query_index=emb_idx + 1,
                    ok=False,
                    ids_count=0,
                    latency_ms=latency_ms,
                    error=f"{type(e).__name__}: {msg}",
                    error_hnsw_hint=hint,
                )
            )
            _emit(
                f"[{_now_iso()}] collection={name} step=query_FAIL loop={i + 1}/{loops} "
                f"latency_ms={latency_ms:.1f} hnsw_hint={hint} error={type(e).__name__}: {msg}",
                log_path,
            )
            break
        time.sleep(sleep_s)

    return report


def main() -> None:
    args = _parse_args()

    # Apply backwards-compatible aliases.
    loops = int(args.loops)
    if args.retries is not None:
        loops = int(args.retries)
    n_results = int(args.n_results)
    if args.top_k is not None:
        n_results = int(args.top_k)

    loops = max(1, loops)
    n_results = max(1, n_results)
    sleep_s = _sleep_seconds(int(args.sleep_ms))

    chroma_path = Path(args.path).resolve()
    output_json = Path(args.output_json)
    log_path = Path(args.log) if args.log else None

    collections = _parse_collections(args.collections) or list(DEFAULT_COLLECTIONS)

    chroma_version = getattr(chromadb, "__version__", "unknown")
    _emit("Chroma Integrity Gate", log_path)
    _emit("-" * 88, log_path)
    _emit(f"[{_now_iso()}] chromadb_version={chroma_version}", log_path)
    _emit(f"[{_now_iso()}] path={chroma_path}", log_path)
    _emit(
        f"[{_now_iso()}] collections={collections} loops={loops} n_results={n_results} sleep_ms={args.sleep_ms}",
        log_path,
    )

    client = chromadb.PersistentClient(path=str(chroma_path))

    dim = _load_expected_dim()
    probe_embeddings = _build_probe_embeddings(dim, list(DEFAULT_TEST_QUERIES))

    reports: list[CollectionReport] = []
    overall_ok = True

    for cname in collections:
        try:
            rep = _check_collection(
                client,
                name=cname,
                loops=loops,
                n_results=n_results,
                sleep_s=sleep_s,
                probe_embeddings=probe_embeddings,
                log_path=log_path,
            )
        except Exception as e:
            rep = CollectionReport(
                name=cname,
                ok=False,
                last_error=f"{type(e).__name__}: {e}",
            )
            _emit(
                f"[{_now_iso()}] collection={cname} step=FATAL_FAIL error={type(e).__name__}: {e}",
                log_path,
            )

        reports.append(rep)
        if not rep.ok:
            overall_ok = False

    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "timestamp": _now_iso(),
        "chromadb_version": chroma_version,
        "path": str(chroma_path),
        "settings": {
            "collections": collections,
            "loops": loops,
            "n_results": n_results,
            "sleep_ms": int(args.sleep_ms),
            "probe_queries": list(DEFAULT_TEST_QUERIES),
            "expected_dim": dim,
        },
        "collections": [asdict(r) for r in reports],
        "ok": overall_ok,
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(f"[{_now_iso()}] report_json={output_json}", log_path)
    _emit(f"[{_now_iso()}] OVERALL={'PASS' if overall_ok else 'FAIL'}", log_path)

    raise SystemExit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
