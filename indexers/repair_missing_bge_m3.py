#!/usr/bin/env python3

import argparse
import json
import os
import sqlite3
import time
from typing import Any

import chromadb

# Optional torch for OOM handling
try:
    import torch
except Exception:
    torch = None


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} | {msg}", flush=True)


def sqlite_get_collection_id(sqlite_path: str, name: str) -> str:
    con = sqlite3.connect(sqlite_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT id FROM collections WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Collection not found in sqlite: {name}")
        return row[0]
    finally:
        con.close()


def sqlite_list_ids(sqlite_path: str, collection_id: str) -> list[str]:
    """
    ChromaDB stores embeddings with segment_id, and segments have collection.
    We need to join through segments to get IDs for a specific collection.
    """
    con = sqlite3.connect(sqlite_path)
    try:
        cur = con.cursor()
        # Join embeddings -> segments -> collection
        cur.execute(
            """
            SELECT DISTINCT e.embedding_id
            FROM embeddings e
            JOIN segments s ON e.segment_id = s.id
            WHERE s.collection = ?
        """,
            (collection_id,),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()


def load_bge_m3(model_name: str, device: str):
    """
    Uses FlagEmbedding if available (recommended for bge-m3).
    Falls back to sentence-transformers if installed and compatible (not always).
    """
    try:
        from FlagEmbedding import BGEM3FlagModel

        use_fp16 = device.startswith("cuda")
        model = BGEM3FlagModel(model_name, use_fp16=use_fp16, device=device)
        log(f"Loaded BGEM3FlagModel: {model_name} on {device}")
        return ("flagembedding", model)
    except Exception as e_flag:
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name, device=device)
            log(f"Loaded SentenceTransformer: {model_name} on {device}")
            return ("sentence_transformers", model)
        except Exception as e_st:
            raise RuntimeError(
                "Could not load embedding model.\n"
                f"FlagEmbedding error: {e_flag}\n"
                f"SentenceTransformers error: {e_st}\n"
                "Install FlagEmbedding: pip install -U FlagEmbedding"
            )


def encode_texts(backend_and_model, texts: list[str], batch_size: int) -> list[list[float]]:
    backend, model = backend_and_model

    if backend == "flagembedding":
        # BGEM3FlagModel.encode returns dict with dense_vecs
        out = model.encode(texts, batch_size=batch_size, max_length=8192)
        dense = out["dense_vecs"]
        return dense.tolist() if hasattr(dense, "tolist") else dense

    # sentence-transformers
    vecs = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=False
    )
    return vecs.tolist() if hasattr(vecs, "tolist") else vecs


def chunked(lst: list[Any], n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n], i


def save_checkpoint(path: str, data: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_checkpoint(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", required=True, help="Chroma persist directory")
    ap.add_argument(
        "--sqlite-path",
        default=None,
        help="Path to chroma.sqlite3 (default: <db-path>/chroma.sqlite3)",
    )
    ap.add_argument("--source", required=True, help="Source collection name (old)")
    ap.add_argument("--target", required=True, help="Target collection name (bge_m3_1024)")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--device", default="cuda", help="cuda or cpu")
    ap.add_argument(
        "--fetch-batch", type=int, default=256, help="How many IDs to fetch docs for per batch"
    )
    ap.add_argument(
        "--embed-batch", type=int, default=32, help="Embedding batch size (auto-reduced on OOM)"
    )
    ap.add_argument("--checkpoint", default="repair_missing_checkpoint.json")
    ap.add_argument("--sleep", type=float, default=0.0, help="Optional sleep between batches")
    args = ap.parse_args()

    sqlite_path = args.sqlite_path or os.path.join(args.db_path, "chroma.sqlite3")
    if not os.path.exists(sqlite_path):
        raise RuntimeError(f"SQLite not found: {sqlite_path}")

    log(f"DB path: {args.db_path}")
    log(f"SQLite: {sqlite_path}")
    log(f"Source: {args.source}")
    log(f"Target: {args.target}")

    # Collection IDs in SQLite
    src_cid = sqlite_get_collection_id(sqlite_path, args.source)
    tgt_cid = sqlite_get_collection_id(sqlite_path, args.target)

    log("Reading IDs from SQLite (this can take a bit)...")
    src_ids = sqlite_list_ids(sqlite_path, src_cid)
    tgt_ids = sqlite_list_ids(sqlite_path, tgt_cid)

    log(f"Source IDs: {len(src_ids)}")
    log(f"Target IDs: {len(tgt_ids)}")

    tgt_set = set(tgt_ids)
    missing_ids = [i for i in src_ids if i not in tgt_set]
    log(f"Missing IDs: {len(missing_ids)}")

    if not missing_ids:
        log("Nothing missing. Done.")
        return 0

    # Chroma client
    client = chromadb.PersistentClient(path=args.db_path)
    src_col = client.get_collection(args.source)
    tgt_col = client.get_collection(args.target)

    # Load model
    backend_and_model = load_bge_m3(args.model, args.device)

    # Checkpoint
    ck = load_checkpoint(args.checkpoint)
    start_at = int(ck.get("next_index", 0))
    if start_at > 0:
        log(f"Resuming from checkpoint index {start_at}/{len(missing_ids)}")

    embed_batch = max(1, args.embed_batch)

    repaired = 0
    for batch_ids, batch_start in chunked(missing_ids[start_at:], args.fetch_batch):
        global_index = start_at + batch_start

        # Fetch from source
        got = src_col.get(ids=batch_ids, include=["documents", "metadatas"])
        ids = got.get("ids", [])
        docs = got.get("documents", [])
        metas = got.get("metadatas", [])

        if not ids:
            log(f"[WARN] Batch at {global_index}: source.get returned no ids. Skipping.")
            save_checkpoint(
                args.checkpoint, {"next_index": global_index + len(batch_ids), "repaired": repaired}
            )
            continue

        # Defensive: remove any None documents
        cleaned = []
        for i, d, m in zip(ids, docs, metas):
            if d is None:
                continue
            cleaned.append((i, d, m if m is not None else {}))

        if not cleaned:
            log(f"[WARN] Batch at {global_index}: all documents None. Skipping.")
            save_checkpoint(
                args.checkpoint, {"next_index": global_index + len(batch_ids), "repaired": repaired}
            )
            continue

        ids_c = [x[0] for x in cleaned]
        docs_c = [x[1] for x in cleaned]
        metas_c = [x[2] for x in cleaned]

        # Embed with OOM backoff
        while True:
            try:
                vecs = encode_texts(backend_and_model, docs_c, batch_size=embed_batch)
                break
            except RuntimeError as e:
                msg = str(e).lower()
                if "out of memory" in msg and args.device.startswith("cuda"):
                    log(f"[OOM] embed_batch={embed_batch} too high. Reducing.")
                    if torch is not None:
                        try:
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                    embed_batch = max(1, embed_batch // 2)
                    if embed_batch == 1:
                        log(
                            "[OOM] embed_batch hit 1. Consider running --device cpu or lowering --fetch-batch."
                        )
                    continue
                raise

        # Write to target (only missing IDs, so add is OK)
        try:
            tgt_col.add(ids=ids_c, documents=docs_c, metadatas=metas_c, embeddings=vecs)
        except Exception as e_add:
            # If your Chroma supports upsert, use it as a fallback
            if hasattr(tgt_col, "upsert"):
                log(f"[WARN] add() failed ({e_add}). Trying upsert()...")
                tgt_col.upsert(ids=ids_c, documents=docs_c, metadatas=metas_c, embeddings=vecs)
            else:
                raise

        repaired += len(ids_c)
        log(
            f"Repaired {repaired}/{len(missing_ids)} (last batch {len(ids_c)}), embed_batch={embed_batch}"
        )

        save_checkpoint(
            args.checkpoint, {"next_index": global_index + len(batch_ids), "repaired": repaired}
        )

        if args.sleep > 0:
            time.sleep(args.sleep)

    # Final verification
    final_tgt_ids = sqlite_list_ids(sqlite_path, tgt_cid)
    log(f"FINAL target embeddings (SQLite): {len(final_tgt_ids)}")
    log("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
