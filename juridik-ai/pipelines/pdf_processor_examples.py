"""
Practical integration examples for using PDF Processor in RAG pipelines

This file contains real-world examples of integrating the PDF processor module
with various RAG and AI components in the Juridik-AI system.
"""

import json
import logging
from pathlib import Path
from typing import Optional

try:
    from pdf_processor import Chunk, PDFProcessor, extract_pdf_text, process_pdf_simple
except ImportError:
    # Handle relative imports when used as part of the package
    from .pdf_processor import Chunk, PDFProcessor, extract_pdf_text

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# Example 1: Basic Batch PDF Processing for RAG
# ============================================================================


def process_document_directory(
    directory: str,
    output_json: str = "chunks_database.json",
    max_tokens: int = 1000,
) -> int:
    """
    Process all PDFs in a directory and save chunks to JSON for RAG system.

    This is useful for batch processing legal documents for a RAG index.

    Args:
        directory: Path to directory containing PDFs
        output_json: Output JSON file for chunks
        max_tokens: Maximum tokens per chunk

    Returns:
        Total number of chunks processed

    Example:
        >>> total = process_document_directory("documents/juridik/")
        >>> print(f"Processed {total} chunks")
    """
    pdf_dir = Path(directory)
    if not pdf_dir.is_dir():
        raise ValueError(f"Directory not found: {directory}")

    processor = PDFProcessor(max_tokens=max_tokens)
    all_chunks = []
    processed_count = 0
    error_count = 0

    logger.info(f"Processing PDFs from: {pdf_dir}")

    for pdf_file in sorted(pdf_dir.glob("**/*.pdf")):
        try:
            logger.info(f"Processing: {pdf_file.relative_to(pdf_dir)}")

            chunks = processor.process_pdf(str(pdf_file))
            all_chunks.extend(chunks)
            processed_count += 1

            logger.info(f"  -> Created {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Error processing {pdf_file.name}: {e}")
            error_count += 1

    # Save to JSON
    output_path = Path(output_json)
    chunk_dicts = [
        {
            "id": f"{chunk.pdf_source}_{chunk.chunk_index}",
            "content": chunk.content,
            "metadata": {
                "source": chunk.pdf_source,
                "page": chunk.source_page,
                "chunk_index": chunk.chunk_index,
                "tokens": chunk.token_estimate,
                "section": chunk.section_header,
            },
        }
        for chunk in all_chunks
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunk_dicts, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(all_chunks)} chunks to {output_json}")
    logger.info(f"Summary: {processed_count} PDFs processed, {error_count} errors")

    return len(all_chunks)


# ============================================================================
# Example 2: Integration with Vector Database (Chroma/Pinecone/etc)
# ============================================================================


def prepare_chunks_for_vector_db(
    pdf_path: str,
    embedding_model: Optional[str] = None,
) -> list[dict]:
    """
    Process PDF and prepare chunks for ingestion into a vector database.

    This format is compatible with Chroma, Pinecone, Weaviate, etc.

    Args:
        pdf_path: Path to PDF file
        embedding_model: Optional embedding model name for metadata

    Returns:
        List of document dictionaries ready for vector DB ingestion

    Example:
        >>> docs = prepare_chunks_for_vector_db("legal_doc.pdf")
        >>> # Use with Chroma:
        >>> # collection.add(ids=[d["id"] for d in docs], metadatas=[d["metadata"] for d in docs], documents=[d["content"] for d in docs])
    """
    processor = PDFProcessor()
    chunks = processor.process_pdf(pdf_path)

    documents = []
    for chunk in chunks:
        doc = {
            "id": f"{Path(pdf_path).stem}_{chunk.chunk_index}",
            "content": chunk.content,
            "metadata": {
                "source": chunk.pdf_source,
                "page": chunk.source_page,
                "chunk_index": chunk.chunk_index,
                "tokens": chunk.token_estimate,
                "section": chunk.section_header,
                "embedding_model": embedding_model or "default",
            },
        }
        documents.append(doc)

    return documents


# ============================================================================
# Example 3: Context-Aware Chunking for Different Use Cases
# ============================================================================


class AdaptiveChunker:
    """
    Adaptively chunk PDFs based on use case and model context window.

    Different LLMs have different context windows:
    - Claude (200K): Can handle large chunks (2000-4000 tokens)
    - GPT-4 (8K/32K/128K): Medium chunks (1000-2000 tokens)
    - Smaller models: Smaller chunks (256-512 tokens)
    """

    CHUNK_SIZES = {
        "small": 256,  # Smaller models, mobile
        "medium": 1000,  # Standard LLMs (default)
        "large": 2000,  # Advanced LLMs (Claude, GPT-4)
        "xlarge": 4000,  # Very large context windows
    }

    @classmethod
    def chunk_for_model(cls, pdf_path: str, model_size: str = "medium") -> list[Chunk]:
        """
        Chunk PDF optimized for a specific model size.

        Args:
            pdf_path: Path to PDF
            model_size: One of "small", "medium", "large", "xlarge"

        Returns:
            Optimized chunks for the model

        Example:
            >>> chunks = AdaptiveChunker.chunk_for_model("doc.pdf", "large")
        """
        if model_size not in cls.CHUNK_SIZES:
            raise ValueError(f"Unknown model size: {model_size}")

        max_tokens = cls.CHUNK_SIZES[model_size]
        processor = PDFProcessor(max_tokens=max_tokens, chunk_overlap=max_tokens // 10)

        return processor.process_pdf(pdf_path)

    @classmethod
    def chunk_with_context_window(cls, pdf_path: str, context_tokens: int = 8000) -> list[Chunk]:
        """
        Chunk based on specific context window size.

        Allocates 30% of context for the question/answer, 70% for document context.

        Args:
            pdf_path: Path to PDF
            context_tokens: Total context window size

        Returns:
            Chunks sized for the context window

        Example:
            >>> chunks = AdaptiveChunker.chunk_with_context_window("doc.pdf", 128000)
        """
        # Allocate 70% for document chunks
        max_chunk_tokens = int(context_tokens * 0.7)
        processor = PDFProcessor(max_tokens=max_chunk_tokens)

        return processor.process_pdf(pdf_path)


# ============================================================================
# Example 4: Swedish Legal Document Processing Pipeline
# ============================================================================


class SwedishLegalDocumentProcessor:
    """
    Specialized processor for Swedish legal documents with metadata extraction.
    """

    # Common Swedish legal document types
    DOCUMENT_TYPES = {
        "lag": "Lag (Law)",
        "förordning": "Förordning (Regulation)",
        "proposition": "Proposition (Government Bill)",
        "bet": "Betänkande (Committee Report)",
        "dom": "Dom (Court Decision)",
        "avtal": "Avtal (Agreement)",
        "memo": "Promemoria (Memorandum)",
    }

    # Swedish legal section headers to look for
    LEGAL_SECTIONS = [
        "1 § Tillämpningsområde",
        "2 § Definition",
        "Ikraftträdande",
        "Övergångsbestämmelser",
        "Ändringsförteckning",
    ]

    @staticmethod
    def detect_document_type(pdf_path: str) -> Optional[str]:
        """
        Detect the type of Swedish legal document.

        Args:
            pdf_path: Path to PDF

        Returns:
            Document type or None if not detected

        Example:
            >>> doc_type = SwedishLegalDocumentProcessor.detect_document_type("lag_2024_12.pdf")
        """
        processor = PDFProcessor()
        text, _ = processor.extract_text(pdf_path)

        text_lower = text.lower()
        for doc_type, description in SwedishLegalDocumentProcessor.DOCUMENT_TYPES.items():
            if doc_type in text_lower:
                return description

        return None

    @staticmethod
    def process_swedish_legal_doc(pdf_path: str) -> dict:
        """
        Full processing pipeline for Swedish legal documents.

        Returns structured data with document metadata and chunks.

        Args:
            pdf_path: Path to PDF

        Returns:
            Dictionary with document info and chunks

        Example:
            >>> result = SwedishLegalDocumentProcessor.process_swedish_legal_doc("lag.pdf")
            >>> print(result["document_type"])
            >>> print(f"Chunks: {len(result['chunks'])}")
        """
        processor = PDFProcessor()
        pdf_path = Path(pdf_path)

        # Extract text and detect type
        text, pdf_type = processor.extract_text(str(pdf_path))
        doc_type = SwedishLegalDocumentProcessor.detect_document_type(str(pdf_path))

        # Process chunks
        chunks = processor.chunk_document(text, str(pdf_path))

        # Extract section headers
        sections = [c.section_header for c in chunks if c.section_header]

        return {
            "filename": pdf_path.name,
            "document_type": doc_type,
            "pdf_type": pdf_type.value,
            "total_chunks": len(chunks),
            "total_tokens": sum(c.token_estimate for c in chunks),
            "sections_found": list(set(sections)),
            "chunks": [c.to_dict() for c in chunks],
        }


# ============================================================================
# Example 5: Quality Metrics and Filtering
# ============================================================================


class ChunkQualityAnalyzer:
    """
    Analyze chunk quality for RAG systems.

    Good chunks should:
    - Have sufficient content length
    - Not be too similar to adjacent chunks (unless intentional overlap)
    - Have balanced token distribution
    """

    @staticmethod
    def analyze_chunks(chunks: list[Chunk]) -> dict:
        """
        Analyze quality metrics of chunks.

        Args:
            chunks: List of chunks to analyze

        Returns:
            Dictionary with quality metrics

        Example:
            >>> metrics = ChunkQualityAnalyzer.analyze_chunks(chunks)
            >>> print(f"Average chunk size: {metrics['avg_chars_per_chunk']}")
        """
        if not chunks:
            return {"error": "No chunks to analyze"}

        content_lengths = [len(c.content) for c in chunks]
        token_counts = [c.token_estimate for c in chunks]

        metrics = {
            "total_chunks": len(chunks),
            "total_tokens": sum(token_counts),
            "avg_chars_per_chunk": sum(content_lengths) / len(chunks),
            "avg_tokens_per_chunk": sum(token_counts) / len(chunks),
            "min_tokens": min(token_counts),
            "max_tokens": max(token_counts),
            "chunks_with_section_header": sum(1 for c in chunks if c.section_header),
        }

        return metrics

    @staticmethod
    def filter_valid_chunks(chunks: list[Chunk], min_chars: int = 50) -> list[Chunk]:
        """
        Filter out low-quality chunks (too short, empty, etc).

        Args:
            chunks: List of chunks
            min_chars: Minimum character count per chunk

        Returns:
            Filtered chunks

        Example:
            >>> valid_chunks = ChunkQualityAnalyzer.filter_valid_chunks(chunks, min_chars=100)
        """
        return [c for c in chunks if len(c.content.strip()) >= min_chars]


# ============================================================================
# Example 6: Integration with LLM Prompt Preparation
# ============================================================================


class RAGPromptBuilder:
    """
    Build RAG prompts using PDF chunks.

    Combines retrieved chunks with user questions for LLM context.
    """

    @staticmethod
    def build_context_prompt(
        query: str, chunks: list[Chunk], max_tokens: int = 4000, language: str = "sv"
    ) -> str:
        """
        Build a prompt with context from chunks for RAG.

        Args:
            query: User question
            chunks: Retrieved chunks to include
            max_tokens: Maximum tokens for context
            language: Language for prompts ("sv" for Swedish, "en" for English)

        Returns:
            Formatted prompt ready for LLM

        Example:
            >>> prompt = RAGPromptBuilder.build_context_prompt(
            ...     query="Vad är gränserna för egendomsrätt?",
            ...     chunks=retrieved_chunks
            ... )
            >>> # Pass prompt to LLM
        """
        if language == "sv":
            context_label = "Kontextinformation från dokument:"
            question_label = "Fråga:"
        else:
            context_label = "Context from documents:"
            question_label = "Question:"

        prompt_parts = [
            f"{context_label}\n",
            "-" * 50,
        ]

        # Add chunks until we hit token limit
        total_tokens = 0
        for chunk in chunks:
            if total_tokens + chunk.token_estimate > max_tokens:
                break

            source_info = f"[{Path(chunk.pdf_source).name}, s. {chunk.source_page}]"
            if chunk.section_header:
                source_info += f" - {chunk.section_header}"

            prompt_parts.append(f"\n{source_info}")
            prompt_parts.append(chunk.content)

            total_tokens += chunk.token_estimate

        prompt_parts.extend(
            [
                "\n" + "-" * 50,
                f"\n{question_label}\n{query}",
            ]
        )

        return "\n".join(prompt_parts)


# ============================================================================
# Example 7: Command-line Integration
# ============================================================================


def main():
    """
    Example command-line usage of PDF processor.
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_processor_examples.py <command> [args]")
        print("\nCommands:")
        print("  batch <directory> - Process all PDFs in directory")
        print("  swedish <pdf_path> - Process Swedish legal document")
        print("  analyze <pdf_path> - Analyze chunks from PDF")
        print("  extract <pdf_path> - Extract text from PDF")
        return

    command = sys.argv[1]

    if command == "batch" and len(sys.argv) > 2:
        directory = sys.argv[2]
        total = process_document_directory(directory)
        print(f"Success: Processed {total} chunks")

    elif command == "swedish" and len(sys.argv) > 2:
        pdf_path = sys.argv[2]
        result = SwedishLegalDocumentProcessor.process_swedish_legal_doc(pdf_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif command == "analyze" and len(sys.argv) > 2:
        pdf_path = sys.argv[2]
        processor = PDFProcessor()
        chunks = processor.process_pdf(pdf_path)
        metrics = ChunkQualityAnalyzer.analyze_chunks(chunks)
        print(json.dumps(metrics, indent=2))

    elif command == "extract" and len(sys.argv) > 2:
        pdf_path = sys.argv[2]
        text = extract_pdf_text(pdf_path)
        print(text)

    else:
        print("Unknown command or missing arguments")


if __name__ == "__main__":
    main()
