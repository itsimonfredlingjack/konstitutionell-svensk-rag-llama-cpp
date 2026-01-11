#!/usr/bin/env python3
"""
Contextual Ingestion Pipeline - Anthropic Contextual Retrieval Implementation

Implements contextual retrieval by enriching document chunks with LLM-generated
context summaries before embedding. This dramatically improves retrieval accuracy
by preserving document context that would otherwise be lost in chunking.

Based on Anthropic's Contextual Retrieval methodology:
- Each chunk gets a context summary (1-2 sentences) describing its place in the document
- Summary is prepended to chunk before embedding
- Original text stored in metadata for display

Usage:
    from contextual_ingestor import ContextualIngestor

    ingestor = ContextualIngestor(
        llm_base_url="http://localhost:8080/v1",
        embedding_model="BAAI/bge-m3"
    )

    chunks = ingestor.process_document(
        full_text="...",
        document_title="GDPR-lagen",
        chunk_size_tokens=500
    )
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.config_service import get_config_service
from app.services.embedding_service import get_embedding_service
from app.services.llm_service import get_llm_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextualChunk:
    """A chunk with contextual summary"""

    original_text: str  # Original chunk text (for display)
    enriched_text: str  # Context summary + original text (for embedding)
    context_summary: str  # Generated context summary
    chunk_index: int
    metadata: dict


class ContextualIngestor:
    """
    Contextual Ingestion Pipeline

    Processes documents by:
    1. Chunking text into ~500 token pieces
    2. Generating context summary for each chunk via LLM
    3. Prepending summary to chunk for embedding
    4. Embedding enriched text with BGE-M3
    5. Storing in ChromaDB with original text in metadata
    """

    def __init__(
        self,
        llm_base_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        context_model: Optional[str] = None,
        chunk_size_tokens: int = 500,
        chunk_overlap_tokens: int = 50,
    ):
        """
        Initialize Contextual Ingestor

        Args:
            llm_base_url: Base URL for LLM API (default: from config)
            embedding_model: Embedding model name (default: BGE-M3 from config)
            context_model: Model for context generation (default: Qwen 0.5B)
            chunk_size_tokens: Target chunk size in tokens
            chunk_overlap_tokens: Overlap between chunks in tokens
        """
        # Get config service
        self.config = get_config_service()

        # LLM for context generation (use lightweight model)
        self.context_model = context_model or "Qwen2.5-0.5B-Instruct-Q8_0.gguf"
        self.llm_base_url = llm_base_url or self.config.llm_base_url

        # Embedding model (BGE-M3)
        self.embedding_model_name = embedding_model or self.config.embedding_model
        self.embedding_service = get_embedding_service(self.config)

        # Chunking config
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

        # LLM service for context generation
        self.llm_service = get_llm_service(self.config)

        logger.info(
            f"ContextualIngestor initialized: "
            f"context_model={self.context_model}, "
            f"embedding={self.embedding_model_name}, "
            f"chunk_size={chunk_size_tokens}"
        )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token for Swedish"""
        return max(1, int(len(text) / 4))

    def _chunk_text(self, text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
        """
        Split text into chunks with overlap

        Args:
            text: Full document text
            max_tokens: Target chunk size in tokens
            overlap_tokens: Overlap between chunks in tokens

        Returns:
            List of chunk texts
        """
        if not text:
            return []

        # Convert token budget to char budget (~4 chars/token)
        max_chars = max(200, max_tokens * 4)
        overlap_chars = overlap_tokens * 4

        chunks: list[str] = []
        step = max(1, max_chars - overlap_chars)
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(text_len, start + max_chars)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start += step

        return chunks

    async def _generate_context_summary(
        self,
        full_document: str,
        chunk_text: str,
        document_title: str = "Dokument",
    ) -> str:
        """
        Generate context summary for a chunk using LLM

        Args:
            full_document: Complete document text for reference
            chunk_text: The specific chunk to summarize context for
            document_title: Title/name of the document

        Returns:
            Context summary (1-2 sentences)
        """
        prompt = f"""Vänligen ge en kort sammanfattning (1-2 meningar) av kontexten för detta textavsnitt.
Vilket dokument, kapitel eller lagrum verkar det tillhöra?

Här är hela dokumentet för referens:
[DOKUMENT_START]
{full_document[:8000]}  # Truncate to avoid token limits
[DOKUMENT_SLUT]

Här är avsnittet:
[CHUNK]
{chunk_text}
[CHUNK_SLUT]

Sammanfattning av kontexten:"""

        messages = [
            {
                "role": "system",
                "content": "Du är en assistent som sammanfattar kontexten för textavsnitt. Ge kortfattade, informativa sammanfattningar (1-2 meningar).",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            # Use lightweight model for context generation
            response, stats = await self.llm_service.chat_complete(
                messages=messages,
                model=self.context_model,
                config_override={
                    "temperature": 0.3,  # Low temperature for factual summaries
                    "num_predict": 150,  # Short summaries
                },
            )

            # Clean up response
            summary = response.strip()
            if not summary:
                # Fallback if LLM returns empty
                summary = f"Textavsnitt från {document_title}"

            return summary

        except Exception as e:
            logger.warning(f"Failed to generate context summary: {e}")
            # Fallback summary
            return f"Textavsnitt från {document_title}"

    async def process_document(
        self,
        full_text: str,
        document_title: str = "Dokument",
        document_metadata: Optional[dict] = None,
    ) -> list[ContextualChunk]:
        """
        Process a document with contextual retrieval

        Args:
            full_text: Complete document text
            document_title: Title/name of the document
            document_metadata: Additional metadata to include

        Returns:
            List of ContextualChunk objects ready for embedding
        """
        logger.info(f"Processing document: {document_title} ({len(full_text)} chars)")

        # Step 1: Chunk the text
        chunks = self._chunk_text(
            full_text,
            max_tokens=self.chunk_size_tokens,
            overlap_tokens=self.chunk_overlap_tokens,
        )

        logger.info(f"Created {len(chunks)} chunks")

        # Step 2: Generate context summaries for each chunk
        contextual_chunks: list[ContextualChunk] = []

        for idx, chunk_text in enumerate(chunks):
            logger.debug(f"Generating context for chunk {idx + 1}/{len(chunks)}")

            # Generate context summary
            context_summary = await self._generate_context_summary(
                full_document=full_text,
                chunk_text=chunk_text,
                document_title=document_title,
            )

            # Create enriched text: [KONTEXT] {summary} \n [TEXT] {original_chunk}
            enriched_text = f"[KONTEXT] {context_summary}\n\n[TEXT] {chunk_text}"

            # Prepare metadata
            metadata = {
                "document_title": document_title,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "page_content": chunk_text,  # Original text for display
                "context_summary": context_summary,
                **(document_metadata or {}),
            }

            contextual_chunks.append(
                ContextualChunk(
                    original_text=chunk_text,
                    enriched_text=enriched_text,
                    context_summary=context_summary,
                    chunk_index=idx,
                    metadata=metadata,
                )
            )

        logger.info(f"Generated {len(contextual_chunks)} contextual chunks")
        return contextual_chunks

    def embed_chunks(self, contextual_chunks: list[ContextualChunk]) -> list[list[float]]:
        """
        Embed contextual chunks using BGE-M3

        Args:
            contextual_chunks: List of ContextualChunk objects

        Returns:
            List of embedding vectors
        """
        # Extract enriched texts for embedding
        enriched_texts = [chunk.enriched_text for chunk in contextual_chunks]

        # Embed using BGE-M3
        embeddings = self.embedding_service.embed(enriched_texts)

        logger.info(f"Embedded {len(embeddings)} chunks")
        return embeddings

    async def process_and_embed(
        self,
        full_text: str,
        document_title: str = "Dokument",
        document_metadata: Optional[dict] = None,
    ) -> tuple[list[ContextualChunk], list[list[float]]]:
        """
        Complete pipeline: process document and generate embeddings

        Args:
            full_text: Complete document text
            document_title: Title/name of the document
            document_metadata: Additional metadata

        Returns:
            Tuple of (contextual_chunks, embeddings)
        """
        # Process document
        chunks = await self.process_document(
            full_text=full_text,
            document_title=document_title,
            document_metadata=document_metadata,
        )

        # Embed chunks
        embeddings = self.embed_chunks(chunks)

        return chunks, embeddings


# Example usage
if __name__ == "__main__":

    async def main():
        ingestor = ContextualIngestor()

        # Example document
        sample_text = """
        Regeringsformen (RF) är en av Sveriges grundlagar. Den fastställer hur staten ska styras.

        Kapitel 1 behandlar statsskicket. Sverige är en demokrati där all makt utgår från folket.

        Kapitel 2 behandlar grundläggande fri- och rättigheter. Alla människor har rätt till liv, frihet och säkerhet.
        """

        chunks, embeddings = await ingestor.process_and_embed(
            full_text=sample_text,
            document_title="Regeringsformen - Exempel",
        )

        print(f"Processed {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(f"\nChunk {i + 1}:")
            print(f"  Context: {chunk.context_summary}")
            print(f"  Original: {chunk.original_text[:100]}...")
            print(f"  Embedding dim: {len(embeddings[i])}")

    asyncio.run(main())
