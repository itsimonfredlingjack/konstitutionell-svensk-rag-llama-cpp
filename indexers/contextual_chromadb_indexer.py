#!/usr/bin/env python3
"""
Contextual ChromaDB Indexer

Integrates ContextualIngestor with ChromaDB for document indexing.
Handles the complete pipeline: contextual processing → embedding → ChromaDB storage.

Usage:
    from contextual_chromadb_indexer import ContextualChromaDBIndexer

    indexer = ContextualChromaDBIndexer(
        collection_name="swedish_gov_docs_bge_m3_1024"
    )

    await indexer.index_document(
        full_text="...",
        document_title="GDPR-lagen",
        document_id="gdpr_2024"
    )
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.config_service import get_config_service
from app.utils.logging import get_logger
from contextual_ingestor import ContextualIngestor

logger = get_logger(__name__)


class ContextualChromaDBIndexer:
    """
    ChromaDB Indexer with Contextual Retrieval

    Processes documents with contextual summaries and stores them in ChromaDB.
    Original text is preserved in metadata for display, while enriched text
    is used for embedding and retrieval.
    """

    def __init__(
        self,
        chromadb_path: Optional[str] = None,
        collection_name: str = "swedish_gov_docs",
        embedding_model: Optional[str] = None,
        context_model: Optional[str] = None,
    ):
        """
        Initialize Contextual ChromaDB Indexer

        Args:
            chromadb_path: Path to ChromaDB data directory
            collection_name: Name of ChromaDB collection
            embedding_model: Embedding model (default: BGE-M3)
            context_model: Model for context generation (default: Qwen 0.5B)
        """
        self.config = get_config_service()

        # ChromaDB setup
        self.chromadb_path = chromadb_path or self.config.chromadb_path
        self.collection_name = collection_name

        # Initialize ChromaDB client
        import chromadb
        import chromadb.config

        settings = chromadb.config.Settings(
            anonymized_telemetry=False,
            allow_reset=True,
        )

        self.chromadb_client = chromadb.PersistentClient(
            path=self.chromadb_path,
            settings=settings,
        )

        # Get or create collection
        try:
            self.collection = self.chromadb_client.get_collection(name=self.collection_name)
            logger.info(
                f"Using existing collection: {self.collection_name} ({self.collection.count()} documents)"
            )
        except Exception:
            # Create collection with BGE-M3 dimensions (1024)
            self.collection = self.chromadb_client.create_collection(
                name=self.collection_name,
                metadata={"description": "Swedish government documents with contextual retrieval"},
            )
            logger.info(f"Created new collection: {self.collection_name}")

        # Initialize contextual ingestor
        self.ingestor = ContextualIngestor(
            embedding_model=embedding_model,
            context_model=context_model,
        )

        logger.info(
            f"ContextualChromaDBIndexer initialized: "
            f"collection={self.collection_name}, "
            f"path={self.chromadb_path}"
        )

    async def index_document(
        self,
        full_text: str,
        document_title: str = "Dokument",
        document_id: Optional[str] = None,
        document_metadata: Optional[dict] = None,
        batch_size: int = 50,
    ) -> dict:
        """
        Index a document with contextual retrieval

        Args:
            full_text: Complete document text
            document_title: Title/name of the document
            document_id: Unique document ID (auto-generated if not provided)
            document_metadata: Additional metadata
            batch_size: Batch size for ChromaDB upsert

        Returns:
            Dict with indexing statistics
        """
        if not document_id:
            document_id = str(uuid.uuid4())

        logger.info(f"Indexing document: {document_title} (ID: {document_id})")

        # Step 1: Process document with contextual retrieval
        chunks, embeddings = await self.ingestor.process_and_embed(
            full_text=full_text,
            document_title=document_title,
            document_metadata={
                "document_id": document_id,
                **(document_metadata or {}),
            },
        )

        # Step 2: Prepare data for ChromaDB
        ids = []
        documents = []  # Enriched text for embedding (already done, but ChromaDB needs it)
        metadatas = []

        for chunk in chunks:
            chunk_id = f"{document_id}_chunk_{chunk.chunk_index}"
            ids.append(chunk_id)

            # Store enriched text in documents field (for reference, embedding already done)
            # Note: ChromaDB will re-embed if we don't provide embeddings, so we provide them
            documents.append(chunk.enriched_text)

            # Metadata with original text for display
            metadata = {
                "document_id": document_id,
                "document_title": document_title,
                "page_content": chunk.original_text,  # Original text for display
                "context_summary": chunk.context_summary,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.metadata.get("total_chunks", len(chunks)),
                **(chunk.metadata.get("document_metadata", {}) or {}),
            }
            metadatas.append(metadata)

        # Step 3: Upsert to ChromaDB in batches
        total_indexed = 0

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_documents = documents[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]

            try:
                self.collection.upsert(
                    ids=batch_ids,
                    documents=batch_documents,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas,
                )
                total_indexed += len(batch_ids)
                logger.debug(f"Indexed batch {i // batch_size + 1}: {len(batch_ids)} chunks")
            except Exception as e:
                logger.error(f"Failed to index batch {i // batch_size + 1}: {e}")
                raise

        logger.info(f"Successfully indexed {total_indexed} chunks for document '{document_title}'")

        return {
            "document_id": document_id,
            "document_title": document_title,
            "chunks_indexed": total_indexed,
            "collection": self.collection_name,
        }

    async def index_documents_batch(
        self,
        documents: list[dict],
        batch_size: int = 50,
    ) -> dict:
        """
        Index multiple documents in batch

        Args:
            documents: List of dicts with keys: full_text, document_title, document_id, metadata
            batch_size: Batch size for ChromaDB operations

        Returns:
            Dict with batch statistics
        """
        results = []
        total_chunks = 0

        for doc in documents:
            try:
                result = await self.index_document(
                    full_text=doc["full_text"],
                    document_title=doc.get("document_title", "Dokument"),
                    document_id=doc.get("document_id"),
                    document_metadata=doc.get("metadata"),
                    batch_size=batch_size,
                )
                results.append(result)
                total_chunks += result["chunks_indexed"]
            except Exception as e:
                logger.error(f"Failed to index document {doc.get('document_id', 'unknown')}: {e}")
                results.append(
                    {
                        "document_id": doc.get("document_id", "unknown"),
                        "error": str(e),
                    }
                )

        return {
            "documents_processed": len(results),
            "documents_successful": len([r for r in results if "error" not in r]),
            "total_chunks_indexed": total_chunks,
            "results": results,
        }

    def get_collection_stats(self) -> dict:
        """Get statistics about the collection"""
        count = self.collection.count()
        return {
            "collection_name": self.collection_name,
            "total_documents": count,
            "chromadb_path": self.chromadb_path,
        }


# Example usage
if __name__ == "__main__":

    async def main():
        indexer = ContextualChromaDBIndexer(collection_name="test_contextual_collection")

        # Example document
        sample_text = """
        Regeringsformen (RF) är en av Sveriges grundlagar. Den fastställer hur staten ska styras.

        Kapitel 1 behandlar statsskicket. Sverige är en demokrati där all makt utgår från folket.

        Kapitel 2 behandlar grundläggande fri- och rättigheter. Alla människor har rätt till liv, frihet och säkerhet.
        """

        result = await indexer.index_document(
            full_text=sample_text,
            document_title="Regeringsformen - Exempel",
            document_id="rf_example_001",
        )

        print(f"Indexed: {result}")
        print(f"Collection stats: {indexer.get_collection_stats()}")

    asyncio.run(main())
