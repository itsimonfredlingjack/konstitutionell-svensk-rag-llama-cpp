#!/usr/bin/env python3
"""
SFS Indexer - Indexerar SFS-lagtexter i ChromaDB med Jina v3 embeddings
=======================================================================

Läser scrapade SFS-filer och indexerar dem i ChromaDB med Jina v3 (1024-dim)
via backend's EmbeddingService (asymmetrisk encoding, retrieval.passage task).

Collection: sfs_lagtext_jina_v3_1024

Användning:
    python sfs_indexer.py                    # Indexera alla SFS-filer
    python sfs_indexer.py --file sfs_1974_152.json  # Indexera specifik fil
    python sfs_indexer.py --stats            # Visa statistik
    python sfs_indexer.py --reset            # Radera och återskapa collection
    python sfs_indexer.py --search "yttrandefrihet"  # Testsök
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings

# Add backend to path for EmbeddingService
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.services.config_service import get_config_service
from app.services.embedding_service import get_embedding_service

# Konfigurera logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
SFS_DATA_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data/sfs"
COLLECTION_NAME = "sfs_lagtext_jina_v3_1024"

# Mappning från kortnamn till läsbart namn
READABLE_NAMES = {
    "RF": "Regeringsformen",
    "TF": "Tryckfrihetsförordningen",
    "YGL": "Yttrandefrihetsgrundlagen",
    "SO": "Successionsordningen",
    "OSL": "Offentlighets- och sekretesslagen",
    "FL": "Förvaltningslagen",
    "FPL": "Förvaltningsprocesslagen",
    "KL": "Kommunallagen",
    "RB": "Rättegångsbalken",
    "BrB": "Brottsbalken",
    "URL": "Upphovsrättslagen",
    "AvtL": "Avtalslagen",
    "SkL": "Skadeståndslagen",
    "LVU": "Lagen om vård av unga",
}


class SFSIndexer:
    """Indexerar SFS-dokument i ChromaDB med Jina v3 embeddings."""

    def __init__(self, chromadb_path=CHROMADB_PATH, sfs_path=SFS_DATA_PATH):
        self.sfs_path = Path(sfs_path)

        # Initiera ChromaDB
        logger.info(f"Ansluter till ChromaDB: {chromadb_path}")
        self.client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )

        # Initiera Jina v3 embedding service from backend
        config = get_config_service()
        self._embedding_service = get_embedding_service(config)
        logger.info(f"Embedding: {config.embedding_model} ({config.expected_embedding_dim}-dim)")

        # Hämta eller skapa collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "description": "Svenska lagtexter (SFS) - primärkällor (Jina v3)",
                "doc_type": "sfs",
                "embedding_model": config.embedding_model,
                "embedding_dim": config.expected_embedding_dim,
                "hnsw:space": "cosine",
            },
        )

        logger.info(f"Collection '{COLLECTION_NAME}' redo, {self.collection.count()} dokument")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate document embeddings using Jina v3 (retrieval.passage task)."""
        return self._embedding_service.embed_document(texts)

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """Generate query embeddings using Jina v3 (retrieval.query task)."""
        return self._embedding_service.embed_query(texts)

    def load_sfs_file(self, filepath):
        """Läs en SFS JSON-fil"""
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Kunde inte läsa {filepath}: {e}")
            return None

    def generate_stable_id(self, sfs_nummer, kapitel, paragraf, text, moment=None):
        """
        Generera STABIL, deterministisk ID för chunk lifecycle.

        Samma juridiska stycke → samma chunk-id över tid.

        ID-struktur: sfs_{nummer}_{kap}_{paragraf}_{moment}_{content_hash}
        """
        normalized_text = " ".join(text.split()).strip().lower()
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:12]

        parts = ["sfs", sfs_nummer.replace(":", "_")]

        if kapitel:
            kap_clean = kapitel.replace(" ", "").replace(".", "")
            parts.append(kap_clean)

        if paragraf:
            para_clean = paragraf.replace(" ", "").replace(".", "")
            parts.append(para_clean)

        if moment:
            moment_clean = moment.replace(" ", "").replace(".", "")
            parts.append(moment_clean)

        parts.append(content_hash)
        return "_".join(parts)

    def _generate_chapter_id(self, sfs_nummer: str, kapitel: str | None) -> str:
        """Generate parent chapter ID: sfs_{nummer}_{kap}"""
        if not kapitel:
            return ""
        kap_clean = kapitel.replace(" ", "").replace(".", "")
        return f"sfs_{sfs_nummer.replace(':', '_')}_{kap_clean}"

    def _build_sibling_ids(self, chunks: list[dict]) -> dict[int, dict[str, str]]:
        """
        Two-pass sibling ID generation.

        Groups chunks by chapter, then links prev/next within each chapter.

        Returns:
            Dict mapping chunk index to {prev_paragraf_id, next_paragraf_id}
        """
        # First pass: generate stable IDs for all chunks
        chunk_ids = []
        for chunk in chunks:
            chunk_id = self.generate_stable_id(
                chunk.get("sfs_nummer", ""),
                chunk.get("kapitel", ""),
                chunk.get("paragraf", ""),
                chunk.get("text", ""),
            )
            chunk_ids.append(chunk_id)

        # Group chunk indices by chapter
        chapter_groups: dict[str, list[int]] = {}
        for idx, chunk in enumerate(chunks):
            chapter_key = chunk.get("kapitel") or "__no_chapter__"
            if chapter_key not in chapter_groups:
                chapter_groups[chapter_key] = []
            chapter_groups[chapter_key].append(idx)

        # Second pass: link siblings within each chapter
        sibling_map: dict[int, dict[str, str]] = {}
        for indices in chapter_groups.values():
            for pos, idx in enumerate(indices):
                prev_id = chunk_ids[indices[pos - 1]] if pos > 0 else ""
                next_id = chunk_ids[indices[pos + 1]] if pos < len(indices) - 1 else ""
                sibling_map[idx] = {
                    "prev_paragraf_id": prev_id,
                    "next_paragraf_id": next_id,
                }

        return sibling_map

    def index_sfs_document(self, sfs_data, batch_size=100):
        """Indexera ett SFS-dokument med alla dess chunks."""
        chunks = sfs_data.get("chunks", [])
        if not chunks:
            logger.warning(f"Inga chunks i {sfs_data.get('sfs_nummer', 'okänd')}")
            return 0

        sfs_nummer = sfs_data["sfs_nummer"]
        kortnamn = sfs_data.get("kortnamn", sfs_nummer)
        titel = sfs_data.get("titel", "")

        logger.info(f"Indexerar {kortnamn} ({sfs_nummer}): {len(chunks)} chunks")

        # Inject sfs_nummer into chunks for sibling ID generation
        for chunk in chunks:
            chunk["sfs_nummer"] = sfs_nummer

        # Build sibling IDs (two-pass)
        sibling_map = self._build_sibling_ids(chunks)

        indexed = 0

        for i in range(0, len(chunks), batch_size):
            batch_indices = range(i, min(i + batch_size, len(chunks)))
            batch = [chunks[j] for j in batch_indices]

            ids = []
            documents = []
            metadatas = []

            for batch_pos, global_idx in enumerate(batch_indices):
                chunk = batch[batch_pos]

                chunk_id = self.generate_stable_id(
                    sfs_nummer,
                    chunk.get("kapitel", ""),
                    chunk.get("paragraf", ""),
                    chunk.get("text", ""),
                )

                # Build searchable text with context
                kapitel_info = ""
                if chunk.get("kapitel"):
                    kapitel_info = f"{chunk['kapitel']}"
                    if chunk.get("kapitel_rubrik"):
                        kapitel_info += f" {chunk['kapitel_rubrik']}"

                paragraf_info = chunk.get("paragraf", "")
                search_text = f"{kortnamn} {kapitel_info} {paragraf_info}\n{chunk['text']}"

                # Display title for UI
                display_title_parts = [kortnamn]
                if chunk.get("kapitel"):
                    display_title_parts.append(chunk["kapitel"])
                if chunk.get("paragraf"):
                    display_title_parts.append(chunk["paragraf"])
                display_title = " ".join(display_title_parts)

                readable_name = READABLE_NAMES.get(kortnamn)
                if readable_name:
                    display_title += f" - {readable_name}"
                elif titel:
                    short_titel = titel.split("(")[0].strip() if "(" in titel else titel
                    if len(short_titel) < 50 and short_titel.lower() != kortnamn.lower():
                        display_title += f" - {short_titel}"

                # Content hash for change detection
                normalized_text = " ".join(chunk.get("text", "").split()).strip().lower()
                content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:12]

                # Sibling IDs
                siblings = sibling_map.get(global_idx, {})

                # Cross-references as JSON string
                cross_refs = chunk.get("cross_refs")
                cross_refs_json = json.dumps(cross_refs, ensure_ascii=False) if cross_refs else ""

                metadata = {
                    # Core identifiers
                    "doc_type": "sfs",
                    "title": display_title,
                    "sfs_nummer": sfs_nummer,
                    "kortnamn": kortnamn,
                    "titel": titel[:200],
                    # Juridisk struktur
                    "kapitel": chunk.get("kapitel") or "",
                    "kapitel_rubrik": (chunk.get("kapitel_rubrik") or "")[:100],
                    "paragraf": chunk.get("paragraf") or "",
                    # Structure-aware annotations (v3.0)
                    "stycke_count": chunk.get("stycke_count", 0),
                    "punkt_count": chunk.get("punkt_count", 0),
                    "cross_refs_json": cross_refs_json,
                    "amendment_ref": chunk.get("amendment_ref") or "",
                    # Parent-child relationships
                    "parent_chapter_id": self._generate_chapter_id(
                        sfs_nummer, chunk.get("kapitel")
                    ),
                    "prev_paragraf_id": siblings.get("prev_paragraf_id", ""),
                    "next_paragraf_id": siblings.get("next_paragraf_id", ""),
                    # Versionshantering
                    "senast_andrad": chunk.get("senast_andrad") or "",
                    "content_hash": content_hash,
                    "parser_version": "3.0",
                    # Källor och spårbarhet
                    "source_url": chunk.get("source_url", ""),
                    "original_chunk_id": chunk.get("chunk_id", ""),
                    "indexed_at": datetime.now().isoformat(),
                    # Felsökning
                    "chunk_length": len(chunk.get("text", "")),
                    "has_kapitel": bool(chunk.get("kapitel")),
                    "has_paragraf": bool(chunk.get("paragraf")),
                }

                ids.append(chunk_id)
                documents.append(search_text)
                metadatas.append(metadata)

            # Generate embeddings with Jina v3 (document/passage task)
            embeddings = self.embed_documents(documents)

            # Add to ChromaDB
            self.collection.add(
                ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
            )

            indexed += len(batch)
            logger.info(f"  Indexerat {indexed}/{len(chunks)} chunks")

        return indexed

    def index_all(self):
        """Indexera alla SFS-filer"""
        stats = {"files_processed": 0, "chunks_indexed": 0, "errors": []}

        sfs_files = list(self.sfs_path.glob("sfs_*.json"))
        sfs_files = [f for f in sfs_files if "fulltext" not in f.name]

        logger.info(f"Hittade {len(sfs_files)} SFS-filer att indexera")

        for filepath in sorted(sfs_files):
            sfs_data = self.load_sfs_file(filepath)
            if not sfs_data:
                stats["errors"].append(str(filepath))
                continue

            sfs_nummer = sfs_data.get("sfs_nummer", "")
            existing = self.collection.get(where={"sfs_nummer": sfs_nummer}, limit=1)

            if existing and existing.get("ids"):
                logger.info(f"Hoppar över {sfs_nummer} - redan indexerad")
                continue

            try:
                chunks_indexed = self.index_sfs_document(sfs_data)
                stats["files_processed"] += 1
                stats["chunks_indexed"] += chunks_indexed
            except Exception as e:
                logger.error(f"Fel vid indexering av {filepath}: {e}")
                stats["errors"].append(f"{filepath}: {e}")

        return stats

    def get_stats(self):
        """Hämta statistik om collection"""
        count = self.collection.count()

        sample = self.collection.get(limit=10000, include=["metadatas"])
        sfs_numbers = set()
        kortnamn_set = set()

        metadatas = sample.get("metadatas") or []
        for meta in metadatas:
            if meta:
                sfs_numbers.add(meta.get("sfs_nummer", ""))
                kortnamn_set.add(meta.get("kortnamn", ""))

        return {
            "collection_name": COLLECTION_NAME,
            "total_chunks": count,
            "unique_laws": len(sfs_numbers),
            "laws": sorted(kortnamn_set),
            "sfs_numbers": sorted(sfs_numbers),
        }

    def search(self, query, n_results=5):
        """Sök i SFS-collection (uses query embedding)"""
        embeddings = self.embed_query([query])

        results = self.collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            formatted.append(
                {
                    "id": ids[i],
                    "text": docs[i][:500] + "..." if len(docs[i]) > 500 else docs[i],
                    "metadata": metas[i],
                    "distance": dists[i],
                }
            )

        return formatted


def main():
    parser = argparse.ArgumentParser(description="SFS Indexer - Indexera lagtexter i ChromaDB")
    parser.add_argument("--file", type=str, help="Indexera specifik fil")
    parser.add_argument("--stats", action="store_true", help="Visa statistik")
    parser.add_argument("--search", type=str, help="Testsök")
    parser.add_argument("--reset", action="store_true", help="Radera och återskapa collection")

    args = parser.parse_args()

    indexer = SFSIndexer()

    if args.reset:
        logger.warning("Raderar collection...")
        indexer.client.delete_collection(COLLECTION_NAME)
        indexer = SFSIndexer()  # Återskapa
        logger.info("Collection återskapad")

    if args.stats:
        stats = indexer.get_stats()
        print("\n=== SFS Collection Statistik ===")
        print(f"Collection: {stats['collection_name']}")
        print(f"Totalt antal chunks: {stats['total_chunks']}")
        print(f"Antal lagar: {stats['unique_laws']}")
        print("\nIndexerade lagar:")
        for law in stats["laws"]:
            print(f"  - {law}")
        return

    if args.search:
        print(f"\nSöker efter: {args.search}\n")
        results = indexer.search(args.search)
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            print(f"{i}. {meta['kortnamn']} {meta['kapitel']} {meta['paragraf']}")
            print(f"   Distance: {r['distance']:.4f}")
            print(
                f"   Stycken: {meta.get('stycke_count', '?')} | Punkt: {meta.get('punkt_count', '?')}"
            )
            print(f"   {r['text'][:200]}...")
            print()
        return

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            filepath = indexer.sfs_path / args.file

        sfs_data = indexer.load_sfs_file(filepath)
        if sfs_data:
            chunks = indexer.index_sfs_document(sfs_data)
            print(f"Indexerade {chunks} chunks från {filepath}")
        return

    # Default: indexera alla
    logger.info("Startar indexering av alla SFS-filer...")
    stats = indexer.index_all()

    print("\n=== Indexering klar ===")
    print(f"Filer processade: {stats['files_processed']}")
    print(f"Chunks indexerade: {stats['chunks_indexed']}")
    if stats["errors"]:
        print(f"Fel: {len(stats['errors'])}")
        for err in stats["errors"]:
            print(f"  - {err}")

    final_stats = indexer.get_stats()
    print(
        f"\nTotal i collection: {final_stats['total_chunks']} chunks "
        f"från {final_stats['unique_laws']} lagar"
    )


if __name__ == "__main__":
    main()
