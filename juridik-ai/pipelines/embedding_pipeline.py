#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime

import psycopg2
import psycopg2.errors
import torch
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer


class EmbeddingPipeline:
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=self.device)
        self.embedding_dim = 384
        print(f"[INFO] Initialized embedding model on device: {self.device}")

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string to 384-dimensional vector."""
        embedding = self.model.encode(text, convert_to_tensor=False)
        return embedding.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed multiple texts in batches for efficiency."""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_tensor=False,
        )
        return [emb.tolist() for emb in embeddings]

    def process_chunks_to_db(self, chunks: list[dict], db_conn) -> int:
        """
        Process chunks and insert embeddings to PostgreSQL.

        Args:
            chunks: List of dicts with keys: id, content, document_id, page_num, char_start, char_end
            db_conn: PostgreSQL connection object

        Returns:
            Number of chunks successfully inserted
        """
        if not chunks:
            return 0

        texts = [chunk["content"] for chunk in chunks]
        print(f"[INFO] Embedding {len(texts)} chunks...")
        embeddings = self.embed_batch(texts)

        print("[INFO] Inserting to database...")
        cursor = db_conn.cursor()

        try:
            records = []
            for chunk, embedding in zip(chunks, embeddings):
                records.append(
                    (
                        chunk.get("id"),
                        chunk.get("document_id"),
                        chunk.get("content"),
                        embedding,
                        chunk.get("page_num"),
                        chunk.get("char_start"),
                        chunk.get("char_end"),
                        datetime.utcnow(),
                    )
                )

            execute_values(
                cursor,
                """
                INSERT INTO chunks (id, document_id, content, embedding, page_num, char_start, char_end, created_at)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                records,
                template="(%s, %s, %s, %s::vector, %s, %s, %s, %s)",
            )

            db_conn.commit()
            inserted = cursor.rowcount
            print(f"[SUCCESS] Inserted {inserted} chunks with embeddings")
            return inserted

        except psycopg2.errors.UndefinedTable:
            print("[ERROR] chunks table does not exist. Create it first.")
            db_conn.rollback()
            return 0
        except Exception as e:
            print(f"[ERROR] Database error: {e}")
            db_conn.rollback()
            return 0
        finally:
            cursor.close()


def load_chunks_from_json(filepath: str) -> list[dict]:
    """Load chunks from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def get_db_connection(connection_string: str):
    """Create PostgreSQL connection."""
    try:
        conn = psycopg2.connect(connection_string)
        print("[INFO] Connected to PostgreSQL")
        return conn
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Embedding pipeline for chunked documents")
    parser.add_argument("--input", required=True, help="Path to chunks.json file")
    parser.add_argument(
        "--db",
        required=True,
        help="PostgreSQL connection string (e.g., postgresql://user:pass@localhost/db)",
    )
    parser.add_argument(
        "--model",
        default="paraphrase-multilingual-MiniLM-L12-v2",
        help="Sentence transformer model name",
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding")

    args = parser.parse_args()

    # Load chunks
    print(f"[INFO] Loading chunks from {args.input}...")
    chunks = load_chunks_from_json(args.input)
    print(f"[INFO] Loaded {len(chunks)} chunks")

    # Initialize pipeline
    pipeline = EmbeddingPipeline(model_name=args.model)

    # Connect to database
    db_conn = get_db_connection(args.db)

    # Process chunks
    inserted = pipeline.process_chunks_to_db(chunks, db_conn)

    # Cleanup
    db_conn.close()
    print(f"[INFO] Pipeline complete. {inserted}/{len(chunks)} chunks embedded and inserted.")


if __name__ == "__main__":
    main()
