#!/usr/bin/env python3
"""
SFS Indexer - Indexerar SFS-lagtexter i ChromaDB
================================================

Läser scrapade SFS-filer och indexerar dem i ChromaDB med KBLab embeddings.
Skapar en separat collection 'sfs_lagtext' för primärkällor.

Användning:
    python sfs_indexer.py                    # Indexera alla SFS-filer
    python sfs_indexer.py --file sfs_1974_152.json  # Indexera specifik fil
    python sfs_indexer.py --stats            # Visa statistik
"""

import argparse
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Konfigurera logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
SFS_DATA_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data/sfs"
COLLECTION_NAME = "sfs_lagtext"

# Embedding model - samma som backend använder
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"


class KBLabEmbeddingFunction:
    """Custom embedding function using KBLab's Swedish BERT model"""

    def __init__(self, model_name=EMBEDDING_MODEL):
        logger.info(f"Laddar embedding-modell: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Modell laddad, dimension: {self.dimension}")

    def __call__(self, input_texts):
        embeddings = self.model.encode(input_texts, convert_to_numpy=True)
        return embeddings.tolist()


class SFSIndexer:
    """Indexerar SFS-dokument i ChromaDB"""

    def __init__(self, chromadb_path=CHROMADB_PATH, sfs_path=SFS_DATA_PATH):
        self.sfs_path = Path(sfs_path)

        # Initiera ChromaDB
        logger.info(f"Ansluter till ChromaDB: {chromadb_path}")
        self.client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )

        # Initiera embedding function
        self.embedding_fn = KBLabEmbeddingFunction()

        # Hämta eller skapa collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "description": "Svenska lagtexter (SFS) - primärkällor",
                "doc_type": "sfs",
                "embedding_model": EMBEDDING_MODEL,
                "hnsw:space": "cosine",
            },
        )

        logger.info(f"Collection '{COLLECTION_NAME}' redo, {self.collection.count()} dokument")

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

        Args:
            sfs_nummer: T.ex. "1974:152"
            kapitel: T.ex. "2 kap."
            paragraf: T.ex. "1 §"
            text: Chunk-text (normaliseras innan hash)
            moment: T.ex. "1 st." (optional)

        Returns:
            Deterministisk ID som är samma vid reindex
        """
        # Normalisera text för stabil hash
        # Ta bort whitespace-variationer, radbrytningar, etc.
        normalized_text = " ".join(text.split())
        normalized_text = normalized_text.strip().lower()

        # Content hash (SHA256 för stabilitet, MD5 för korthet)
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:12]

        # Bygg deterministisk ID
        # Format: sfs_1974_152_2kap_1§_abc123def456
        parts = ["sfs", sfs_nummer.replace(":", "_")]

        if kapitel:
            # Normalisera kapitel: "2 kap." → "2kap"
            kap_clean = kapitel.replace(" ", "").replace(".", "")
            parts.append(kap_clean)

        if paragraf:
            # Normalisera paragraf: "1 §" → "1§"
            para_clean = paragraf.replace(" ", "").replace(".", "")
            parts.append(para_clean)

        if moment:
            # Normalisera moment: "1 st." → "1st"
            moment_clean = moment.replace(" ", "").replace(".", "")
            parts.append(moment_clean)

        # Lägg till content hash sist
        parts.append(content_hash)

        # Kombinera med underscore
        stable_id = "_".join(parts)

        return stable_id

    def index_sfs_document(self, sfs_data, batch_size=100):
        """Indexera ett SFS-dokument med alla dess chunks"""
        chunks = sfs_data.get("chunks", [])
        if not chunks:
            logger.warning(f"Inga chunks i {sfs_data.get('sfs_nummer', 'okänd')}")
            return 0

        sfs_nummer = sfs_data["sfs_nummer"]
        kortnamn = sfs_data.get("kortnamn", sfs_nummer)
        titel = sfs_data.get("titel", "")

        logger.info(f"Indexerar {kortnamn} ({sfs_nummer}): {len(chunks)} chunks")

        indexed = 0

        # Processa i batchar
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]

            ids = []
            documents = []
            metadatas = []

            for idx, chunk in enumerate(batch):
                # Skapa STABIL, deterministisk ID
                chunk_id = self.generate_stable_id(
                    sfs_nummer,
                    chunk.get("kapitel", ""),
                    chunk.get("paragraf", ""),
                    chunk.get("text", ""),
                    moment=None,  # TODO: Extrahera moment från text om det finns
                )

                # Skapa sökbar text med kontext
                kapitel_info = ""
                if chunk.get("kapitel"):
                    kapitel_info = f"{chunk['kapitel']}"
                    if chunk.get("kapitel_rubrik"):
                        kapitel_info += f" {chunk['kapitel_rubrik']}"

                paragraf_info = chunk.get("paragraf", "")

                # Kombinera för bättre sökbarhet
                search_text = f"{kortnamn} {kapitel_info} {paragraf_info}\n{chunk['text']}"

                # Skapa beskrivande titel för visning i UI
                # Format: "RF 2 kap. 1 § - Regeringsformen" eller "BrB 3 kap. 1 § - Brottsbalken"
                display_title_parts = [kortnamn]
                if chunk.get("kapitel"):
                    display_title_parts.append(chunk["kapitel"])
                if chunk.get("paragraf"):
                    display_title_parts.append(chunk["paragraf"])
                display_title = " ".join(display_title_parts)

                # Mappning från kortnamn till läsbart namn
                READABLE_NAMES = {
                    "RF": "Regeringsformen",
                    "TF": "Tryckfrihetsförordningen",
                    "YGL": "Yttrandefrihetsgrundlagen",
                    "SO": "Successionsordningen",
                    "OSL": "Offentlighets- och sekretesslagen",
                    "FL": "Förvaltningslagen",
                    "KL": "Kommunallagen",
                    "RB": "Rättegångsbalken",
                    "BrB": "Brottsbalken",
                    "URL": "Upphovsrättslagen",
                    "AvtL": "Avtalslagen",
                    "SkL": "Skadeståndslagen",
                    "LVU": "Lagen om vård av unga",
                }

                # Lägg till läsbart namn
                readable_name = READABLE_NAMES.get(kortnamn)
                if readable_name:
                    display_title += f" - {readable_name}"
                elif titel:
                    # Fallback: extrahera kort version av titeln
                    short_titel = titel.split("(")[0].strip() if "(" in titel else titel
                    if len(short_titel) < 50 and short_titel.lower() != kortnamn.lower():
                        display_title += f" - {short_titel}"

                # RIK METADATA för felsökning och chunk lifecycle
                # Normalisera text för content_hash
                normalized_text = " ".join(chunk.get("text", "").split()).strip().lower()
                content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:12]

                metadata = {
                    # Core identifiers
                    "doc_type": "sfs",  # VIKTIGT: Identifierar primärkälla
                    "title": display_title,  # För backend SearchResult.title
                    "sfs_nummer": sfs_nummer,
                    "kortnamn": kortnamn,
                    "titel": titel[:200],  # Fullständig titel
                    # Juridisk struktur
                    "kapitel": chunk.get("kapitel") or "",
                    "kapitel_rubrik": (chunk.get("kapitel_rubrik") or "")[:100],
                    "paragraf": chunk.get("paragraf") or "",
                    "moment": "",  # TODO: Extrahera från text
                    # Versionshantering
                    "senast_andrad": chunk.get("senast_andrad") or "",
                    "content_hash": content_hash,  # För change detection
                    "parser_version": "2.0",  # Öka vid parser-ändringar
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

            # Generera embeddings
            embeddings = self.embedding_fn(documents)

            # Lägg till i ChromaDB
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
        # Filtrera bort fulltext-filer
        sfs_files = [f for f in sfs_files if "fulltext" not in f.name]

        logger.info(f"Hittade {len(sfs_files)} SFS-filer att indexera")

        for filepath in sorted(sfs_files):
            sfs_data = self.load_sfs_file(filepath)
            if not sfs_data:
                stats["errors"].append(str(filepath))
                continue

            # Kolla om redan indexerad
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

        # Hämta unika SFS-nummer
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
        """Sök i SFS-collection"""
        embeddings = self.embedding_fn([query])

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

    # Visa slutlig statistik
    final_stats = indexer.get_stats()
    print(
        f"\nTotal i collection: {final_stats['total_chunks']} chunks från {final_stats['unique_laws']} lagar"
    )


if __name__ == "__main__":
    main()
