"""
PDF Processing Module for RAG (Retrieval-Augmented Generation)

Handles extraction and intelligent chunking of PDF documents with support for:
- Swedish characters (åäö) and Unicode
- Header/footer/page number removal
- Section-aware chunking with overlap
- Metadata preservation (page numbers, chunk indices)
- OCR detection and graceful degradation
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import tiktoken

# Try importing PDF libraries in order of preference
try:
    import pdfplumber

    PDF_LIBRARY = "pdfplumber"
except ImportError:
    try:
        import PyPDF2

        PDF_LIBRARY = "pypdf"
    except ImportError:
        PDF_LIBRARY = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFType(Enum):
    """Enum for PDF type detection"""

    TEXT_BASED = "text_based"
    OCR_BASED = "ocr_based"
    UNKNOWN = "unknown"


@dataclass
class Chunk:
    """
    Represents a chunk of processed document text with metadata

    Attributes:
        content: The text content of the chunk
        chunk_index: Sequential index of this chunk in the document
        source_page: Page number(s) where this chunk originates (1-indexed)
        token_estimate: Estimated token count for the chunk
        pdf_source: Path to the source PDF file
        section_header: Header/section this chunk belongs to (if detected)
    """

    content: str
    chunk_index: int
    source_page: int
    token_estimate: int
    pdf_source: str
    section_header: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert chunk to dictionary format"""
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "source_page": self.source_page,
            "token_estimate": self.token_estimate,
            "pdf_source": self.pdf_source,
            "section_header": self.section_header,
        }


class TextCleaner:
    """Utilities for cleaning extracted PDF text"""

    # Common header/footer patterns
    HEADER_FOOTER_PATTERNS = [
        r"^\s*Page\s+\d+\s*$",  # Page numbers
        r"^\s*\d+\s*$",  # Standalone numbers
        r"^\s*[^\w]*\d+[^\w]*$",  # Numbers with decorations
        r"^\s*https?://\S+\s*$",  # URLs
        r"^\s*[A-Z\d]{3,}[-\s]*\d+\s*$",  # Document IDs
    ]

    # Patterns for detecting section headers
    SECTION_HEADER_PATTERNS = [
        r"^#{1,6}\s+\w+",  # Markdown headers
        r"^[A-Z][A-Z\s]+$",  # ALL CAPS headers
        r"^\d+(\.\d+)*\s+[A-Z]\w+",  # Numbered sections (1. Title)
        r"^[A-Z]\w+\s*-\s*\w+",  # Title - Subtitle
    ]

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean extracted text by removing common artifacts

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            # Skip header/footer patterns
            if any(
                re.match(pattern, line.strip(), re.IGNORECASE)
                for pattern in TextCleaner.HEADER_FOOTER_PATTERNS
            ):
                continue

            # Preserve the line
            cleaned_lines.append(line)

        # Join and normalize whitespace
        text = "\n".join(cleaned_lines)

        # Fix common issues
        # Remove excessive newlines (more than 2 consecutive)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Fix space before punctuation (common in PDFs)
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)

        # Fix broken words (common in PDFs with bad extraction)
        text = re.sub(r"(\w+)\s+(\w{1,2})\s+(\w+)", r"\1\2\3", text)

        # Normalize unicode and Swedish characters
        text = text.replace("–", "-")  # En dash to hyphen
        text = text.replace("—", "-")  # Em dash to hyphen
        text = text.replace(
            """, '"')  # Smart quotes
        text = text.replace(""",
            '"',
        )
        text = text.replace("'", "'")
        text = text.replace("'", "'")

        return text.strip()

    @staticmethod
    def detect_section_header(line: str) -> bool:
        """
        Detect if a line is a section header

        Args:
            line: Line to check

        Returns:
            True if line appears to be a section header
        """
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            return False

        # Check against patterns
        for pattern in TextCleaner.SECTION_HEADER_PATTERNS:
            if re.match(pattern, stripped):
                return True

        # Check if line is short and followed by multiple capitals
        words = stripped.split()
        if len(words) <= 5 and len(stripped) < 80:
            if sum(1 for w in words if w[0].isupper()) / len(words) > 0.7:
                return True

        return False


class TokenEstimator:
    """Estimate token counts for chunks"""

    def __init__(self, model: str = "gpt2"):
        """
        Initialize token estimator

        Args:
            model: Model to use for tokenization (gpt2, cl100k_base, p50k_base)
        """
        try:
            self.encoding = tiktoken.get_encoding(model)
            self.use_tiktoken = True
        except Exception as e:
            logger.warning(
                f"Could not load tiktoken model {model}: {e}. Using fallback estimation."
            )
            self.use_tiktoken = False

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        if self.use_tiktoken:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning(f"Error estimating tokens with tiktoken: {e}")

        # Fallback: simple heuristic (1 token ≈ 4 chars, adjusting for Swedish)
        # Swedish words tend to be slightly longer, so we use conservative 3.5
        char_count = len(text)
        return max(1, int(char_count / 3.5))


class PDFProcessor:
    """
    Main class for processing PDFs for RAG pipelines

    Handles text extraction, cleaning, and intelligent chunking with metadata
    """

    def __init__(self, max_tokens: int = 1000, chunk_overlap: int = 100):
        """
        Initialize PDF processor

        Args:
            max_tokens: Maximum tokens per chunk (default 1000)
            chunk_overlap: Character overlap between chunks (default 100)
        """
        if PDF_LIBRARY is None:
            raise ImportError(
                "No PDF library found. Install 'pdfplumber' or 'pypdf2': " "pip install pdfplumber"
            )

        self.max_tokens = max_tokens
        self.chunk_overlap = chunk_overlap
        self.token_estimator = TokenEstimator()
        self.text_cleaner = TextCleaner()

        logger.info(f"PDFProcessor initialized using {PDF_LIBRARY}")
        logger.info(f"Config: max_tokens={max_tokens}, overlap={chunk_overlap}")

    def extract_text(self, pdf_path: str) -> tuple[str, PDFType]:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (extracted_text, pdf_type)

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ValueError: If PDF cannot be read
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Extracting text from: {pdf_path}")

        extracted_text = ""
        pdf_type = PDFType.UNKNOWN

        if PDF_LIBRARY == "pdfplumber":
            extracted_text, pdf_type = self._extract_with_pdfplumber(pdf_path)
        elif PDF_LIBRARY == "pypdf":
            extracted_text, pdf_type = self._extract_with_pypdf(pdf_path)
        else:
            raise ValueError(f"Unsupported PDF library: {PDF_LIBRARY}")

        if not extracted_text.strip():
            logger.warning(f"No text extracted from {pdf_path}. PDF might be image-based.")
            pdf_type = PDFType.OCR_BASED

        # Clean the extracted text
        extracted_text = self.text_cleaner.clean_text(extracted_text)

        logger.info(
            f"Extracted {len(extracted_text)} characters from {pdf_path} "
            f"(Type: {pdf_type.value})"
        )

        return extracted_text, pdf_type

    def _extract_with_pdfplumber(self, pdf_path: Path) -> tuple[str, PDFType]:
        """
        Extract text using pdfplumber library

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (text, pdf_type)
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []

                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        # Extract text from page
                        text = page.extract_text() or ""

                        # Detect if page has structured content (tables, etc.)
                        tables = page.extract_tables()

                        # Add tables if found
                        if tables:
                            for table in tables:
                                table_text = "\n".join(
                                    [
                                        " | ".join(str(cell) if cell else "" for cell in row)
                                        for row in table
                                    ]
                                )
                                text += "\n\n" + table_text

                        pages_text.append(text)

                    except Exception as e:
                        logger.warning(
                            f"Error extracting text from page {page_num} in {pdf_path}: {e}"
                        )
                        pages_text.append("")

                combined_text = "\n\n".join(pages_text)

                # Detect PDF type based on extracted content
                pdf_type = (
                    PDFType.TEXT_BASED if len(combined_text.split()) > 100 else PDFType.OCR_BASED
                )

                return combined_text, pdf_type

        except Exception as e:
            raise ValueError(f"Failed to extract text with pdfplumber: {e}")

    def _extract_with_pypdf(self, pdf_path: Path) -> tuple[str, PDFType]:
        """
        Extract text using PyPDF2 library (fallback)

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (text, pdf_type)
        """
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages_text = []

                for page_num, page in enumerate(reader.pages, 1):
                    try:
                        text = page.extract_text() or ""
                        pages_text.append(text)
                    except Exception as e:
                        logger.warning(
                            f"Error extracting text from page {page_num} in {pdf_path}: {e}"
                        )
                        pages_text.append("")

                combined_text = "\n\n".join(pages_text)

                # Detect PDF type
                pdf_type = (
                    PDFType.TEXT_BASED if len(combined_text.split()) > 100 else PDFType.OCR_BASED
                )

                return combined_text, pdf_type

        except Exception as e:
            raise ValueError(f"Failed to extract text with PyPDF2: {e}")

    def chunk_document(self, text: str, pdf_source: str = "") -> list[Chunk]:
        """
        Intelligently chunk document text

        Strategy:
        1. First try to split by section headers
        2. Fall back to paragraph splitting
        3. Ensure chunks are within max_tokens
        4. Add overlap for context preservation

        Args:
            text: Cleaned text to chunk
            pdf_source: Source PDF file path for metadata

        Returns:
            List of Chunk objects with metadata
        """
        logger.info(f"Chunking document ({len(text)} characters)")

        chunks = []
        chunk_index = 0

        # Split by section headers first
        sections = self._split_by_sections(text)

        for section_header, section_text in sections:
            # Within each section, split by paragraphs
            paragraphs = section_text.split("\n\n")

            current_chunk = ""
            section_chunks = 0

            for paragraph in paragraphs:
                # Skip empty paragraphs
                if not paragraph.strip():
                    continue

                # Estimate tokens for paragraph
                para_tokens = self.token_estimator.estimate_tokens(paragraph)

                # Add to current chunk if it fits
                if not current_chunk:
                    # Start new chunk
                    current_chunk = paragraph

                else:
                    # Check if adding paragraph would exceed max
                    combined = current_chunk + "\n\n" + paragraph
                    combined_tokens = self.token_estimator.estimate_tokens(combined)

                    if combined_tokens <= self.max_tokens:
                        current_chunk = combined
                    else:
                        # Save current chunk and start new one
                        chunk_obj = self._create_chunk(
                            current_chunk,
                            chunk_index,
                            section_header,
                            pdf_source,
                        )
                        chunks.append(chunk_obj)
                        chunk_index += 1

                        # Add overlap from end of previous chunk
                        current_chunk = self._get_overlap_text(current_chunk) + paragraph
                        section_chunks += 1

            # Don't forget the last chunk
            if current_chunk.strip():
                chunk_obj = self._create_chunk(
                    current_chunk,
                    chunk_index,
                    section_header,
                    pdf_source,
                )
                chunks.append(chunk_obj)
                chunk_index += 1

        logger.info(f"Created {len(chunks)} chunks from document")

        return chunks

    def _split_by_sections(self, text: str) -> list[tuple[Optional[str], str]]:
        """
        Split text by section headers

        Args:
            text: Text to split

        Returns:
            List of (section_header, section_text) tuples
        """
        sections = []
        current_section_header = None
        current_section_text = ""

        for line in text.split("\n"):
            if self.text_cleaner.detect_section_header(line):
                # Save previous section
                if current_section_text.strip():
                    sections.append((current_section_header, current_section_text))

                # Start new section
                current_section_header = line.strip()
                current_section_text = ""
            else:
                current_section_text += line + "\n"

        # Don't forget last section
        if current_section_text.strip():
            sections.append((current_section_header, current_section_text))

        # If no sections found, return whole text
        if not sections:
            sections = [(None, text)]

        return sections

    def _get_overlap_text(self, text: str) -> str:
        """
        Get the last N characters for overlap (up to chunk_overlap)

        Args:
            text: Text to extract overlap from

        Returns:
            Overlap text
        """
        if len(text) <= self.chunk_overlap:
            return ""

        # Find a good break point in the overlap (at a sentence boundary)
        overlap_start = len(text) - self.chunk_overlap
        overlap = text[overlap_start:]

        # Try to find a sentence boundary
        for boundary in [".\n", ".\n\n", "!\n", "?\n"]:
            if boundary in overlap:
                pos = overlap.find(boundary) + 1
                return overlap[pos:].strip()

        # If no sentence boundary, use last newline
        if "\n" in overlap:
            pos = overlap.rfind("\n")
            return overlap[pos:].strip()

        return overlap

    def _create_chunk(
        self,
        content: str,
        chunk_index: int,
        section_header: Optional[str],
        pdf_source: str,
    ) -> Chunk:
        """
        Create a Chunk object with metadata

        Args:
            content: Chunk text content
            chunk_index: Sequential chunk index
            section_header: Section header if any
            pdf_source: Source PDF path

        Returns:
            Chunk object
        """
        token_estimate = self.token_estimator.estimate_tokens(content)

        # Estimate page number from character position (rough estimate)
        # Assuming ~3000 chars per page
        estimated_page = max(1, len(content) // 3000) if pdf_source else 1

        return Chunk(
            content=content.strip(),
            chunk_index=chunk_index,
            source_page=estimated_page,
            token_estimate=token_estimate,
            pdf_source=str(pdf_source),
            section_header=section_header,
        )

    def process_pdf(self, pdf_path: str) -> list[Chunk]:
        """
        End-to-end PDF processing: extract, clean, and chunk

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of Chunk objects ready for RAG

        Raises:
            FileNotFoundError: If PDF doesn't exist
            ValueError: If PDF cannot be processed
        """
        # Extract text
        text, pdf_type = self.extract_text(pdf_path)

        # Warn if OCR detected
        if pdf_type == PDFType.OCR_BASED:
            logger.warning(f"PDF {pdf_path} appears to be OCR-based. Text quality may be reduced.")

        # Chunk the text
        chunks = self.chunk_document(text, pdf_source=str(pdf_path))

        return chunks


# Convenience functions for simple usage
def process_pdf_simple(pdf_path: str, max_tokens: int = 1000) -> list[dict]:
    """
    Simple function to process a PDF and return chunks as dictionaries

    Args:
        pdf_path: Path to PDF file
        max_tokens: Maximum tokens per chunk

    Returns:
        List of chunk dictionaries

    Example:
        >>> chunks = process_pdf_simple("document.pdf")
        >>> for chunk in chunks:
        ...     print(f"Chunk {chunk['chunk_index']}: {chunk['content'][:50]}...")
    """
    processor = PDFProcessor(max_tokens=max_tokens)
    chunks = processor.process_pdf(pdf_path)
    return [chunk.to_dict() for chunk in chunks]


def extract_pdf_text(pdf_path: str) -> str:
    """
    Simple function to extract text from PDF

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted and cleaned text

    Example:
        >>> text = extract_pdf_text("document.pdf")
        >>> print(text)
    """
    processor = PDFProcessor()
    text, _ = processor.extract_text(pdf_path)
    return text


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        max_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else 1000

        processor = PDFProcessor(max_tokens=max_tokens)
        chunks = processor.process_pdf(pdf_file)

        print(f"\nProcessed {len(chunks)} chunks from {pdf_file}\n")
        for chunk in chunks[:3]:  # Print first 3 chunks
            print(f"Chunk {chunk.chunk_index} (Page {chunk.source_page}):")
            print(f"Tokens: {chunk.token_estimate}")
            if chunk.section_header:
                print(f"Section: {chunk.section_header}")
            print(f"Content preview: {chunk.content[:100]}...")
            print("-" * 80)
    else:
        print("Usage: python pdf_processor.py <pdf_path> [max_tokens]")
        print("\nExample: python pdf_processor.py document.pdf 1000")
