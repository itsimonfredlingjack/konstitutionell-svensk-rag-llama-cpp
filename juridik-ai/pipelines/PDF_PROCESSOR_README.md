# PDF Processor Module

A comprehensive Python module for extracting text from PDF files and intelligently chunking them for RAG (Retrieval-Augmented Generation) pipelines.

## Features

- **Robust PDF Text Extraction**: Supports both pdfplumber (primary) and PyPDF2 (fallback)
- **Swedish Character Support**: Correctly handles åäö and other Unicode characters
- **Intelligent Chunking**:
  - Section-aware splitting (preserves document structure)
  - Paragraph-level fallback splitting
  - Configurable token limits (~1000 tokens default)
  - Overlap between chunks for context preservation
- **Metadata Preservation**: Each chunk includes source page, section header, and token estimates
- **OCR Detection**: Warns when processing scanned/OCR-based PDFs
- **Header/Footer Removal**: Automatically cleans extracted text
- **Token Counting**: Uses tiktoken for accurate token estimation (with fallback heuristics)

## Installation

```bash
pip install -r requirements.txt
```

This installs:
- `pdfplumber>=0.10.0` - Primary PDF extraction library
- `PyPDF2>=4.0.0` - Fallback PDF extraction library
- `tiktoken>=0.5.0` - Token counting for LLM compatibility

## Quick Start

### Simple Usage

```python
from pipelines.pdf_processor import process_pdf_simple

# Process a PDF and get chunks as dictionaries
chunks = process_pdf_simple("document.pdf")

for chunk in chunks:
    print(f"Chunk {chunk['chunk_index']} (Page {chunk['source_page']}):")
    print(f"Tokens: {chunk['token_estimate']}")
    print(f"Content: {chunk['content'][:100]}...")
```

### Using the PDFProcessor Class

```python
from pipelines.pdf_processor import PDFProcessor

# Initialize with custom settings
processor = PDFProcessor(
    max_tokens=1000,      # Maximum tokens per chunk
    chunk_overlap=100     # Character overlap between chunks
)

# Process a PDF
chunks = processor.process_pdf("document.pdf")

# Access chunk data
for chunk in chunks:
    print(f"Chunk {chunk.chunk_index}:")
    print(f"  Content: {chunk.content}")
    print(f"  Page: {chunk.source_page}")
    print(f"  Tokens: {chunk.token_estimate}")
    print(f"  Section: {chunk.section_header}")
```

### Extract Text Only

```python
from pipelines.pdf_processor import extract_pdf_text

# Extract and clean text from PDF
text = extract_pdf_text("document.pdf")
print(text)
```

## API Reference

### PDFProcessor Class

Main class for processing PDFs.

#### Initialization

```python
processor = PDFProcessor(max_tokens=1000, chunk_overlap=100)
```

**Parameters:**
- `max_tokens` (int): Maximum tokens per chunk (default: 1000)
- `chunk_overlap` (int): Character overlap between chunks (default: 100)

#### Methods

##### `extract_text(pdf_path: str) -> Tuple[str, PDFType]`

Extract text from a PDF file.

```python
text, pdf_type = processor.extract_text("document.pdf")
# pdf_type is either PDFType.TEXT_BASED or PDFType.OCR_BASED
```

**Returns:**
- Tuple of (cleaned_text, pdf_type)
- Raises `FileNotFoundError` if PDF doesn't exist
- Raises `ValueError` if PDF cannot be read

##### `chunk_document(text: str, pdf_source: str = "") -> List[Chunk]`

Split text into chunks with intelligent section detection.

```python
chunks = processor.chunk_document(text, pdf_source="path/to/document.pdf")
```

**Returns:**
- List of `Chunk` objects with metadata

##### `process_pdf(pdf_path: str) -> List[Chunk]`

End-to-end processing: extract, clean, and chunk.

```python
chunks = processor.process_pdf("document.pdf")
```

**Returns:**
- List of `Chunk` objects ready for RAG

### Chunk Dataclass

Represents a processed chunk with metadata.

```python
@dataclass
class Chunk:
    content: str              # The text content
    chunk_index: int          # Sequential chunk number
    source_page: int          # Page number (1-indexed)
    token_estimate: int       # Estimated token count
    pdf_source: str           # Path to source PDF
    section_header: Optional[str]  # Section header if detected
```

**Methods:**
- `to_dict()` - Convert to dictionary for JSON serialization

### TextCleaner Class

Utility for cleaning extracted PDF text.

```python
cleaner = TextCleaner()

# Clean text
cleaned = cleaner.clean_text(raw_text)

# Detect section headers
is_header = cleaner.detect_section_header(line)
```

### TokenEstimator Class

Estimate token counts for text chunks.

```python
estimator = TokenEstimator(model="gpt2")

# Estimate tokens
token_count = estimator.estimate_tokens(text)
```

**Parameters:**
- `model` (str): Model for tokenization ("gpt2", "cl100k_base", "p50k_base")

## Usage Examples

### Example 1: Basic PDF Processing

```python
from pipelines.pdf_processor import PDFProcessor

processor = PDFProcessor()
chunks = processor.process_pdf("legal_document.pdf")

print(f"Processed into {len(chunks)} chunks")
for chunk in chunks:
    print(f"  Chunk {chunk.chunk_index}: {chunk.token_estimate} tokens")
```

### Example 2: Processing Multiple PDFs

```python
from pathlib import Path
from pipelines.pdf_processor import PDFProcessor

processor = PDFProcessor(max_tokens=1500)

# Process all PDFs in a directory
pdf_dir = Path("documents/")
all_chunks = []

for pdf_file in pdf_dir.glob("*.pdf"):
    try:
        chunks = processor.process_pdf(str(pdf_file))
        all_chunks.extend(chunks)
        print(f"Processed {pdf_file.name}: {len(chunks)} chunks")
    except Exception as e:
        print(f"Error processing {pdf_file.name}: {e}")

print(f"Total chunks: {len(all_chunks)}")
```

### Example 3: Custom Chunk Size for Different Use Cases

```python
from pipelines.pdf_processor import PDFProcessor

# Small chunks for detailed retrieval
processor_small = PDFProcessor(max_tokens=256, chunk_overlap=50)
small_chunks = processor_small.process_pdf("document.pdf")

# Large chunks for context-rich retrieval
processor_large = PDFProcessor(max_tokens=2048, chunk_overlap=200)
large_chunks = processor_large.process_pdf("document.pdf")
```

### Example 4: Handling Swedish Documents

```python
from pipelines.pdf_processor import PDFProcessor

# The processor automatically handles Swedish characters (åäö)
processor = PDFProcessor()
chunks = processor.process_pdf("juridisk_dokument.pdf")

# All Swedish text is preserved and correctly encoded
for chunk in chunks:
    assert "å" in chunk.content or "ä" in chunk.content or "ö" in chunk.content
```

### Example 5: Filtering by Content

```python
from pipelines.pdf_processor import PDFProcessor

processor = PDFProcessor()
chunks = processor.process_pdf("document.pdf")

# Filter chunks by token size
large_chunks = [c for c in chunks if c.token_estimate > 500]

# Filter chunks by page
first_page_chunks = [c for c in chunks if c.source_page == 1]

# Filter chunks by section
intro_chunks = [c for c in chunks if c.section_header and "intro" in c.section_header.lower()]
```

### Example 6: Preparing for RAG/Vector Database

```python
from pipelines.pdf_processor import PDFProcessor
import json

processor = PDFProcessor()
chunks = processor.process_pdf("document.pdf")

# Convert to format suitable for vector database
documents = []
for chunk in chunks:
    doc = {
        "id": f"{chunk.pdf_source}_{chunk.chunk_index}",
        "content": chunk.content,
        "metadata": {
            "source": chunk.pdf_source,
            "page": chunk.source_page,
            "chunk_index": chunk.chunk_index,
            "tokens": chunk.token_estimate,
            "section": chunk.section_header,
        }
    }
    documents.append(doc)

# Save to JSON for ingestion into vector database
with open("chunks.json", "w") as f:
    json.dump(documents, f, indent=2, ensure_ascii=False)
```

## Command Line Usage

Run the module directly for testing:

```bash
python pipelines/pdf_processor.py <pdf_path> [max_tokens]

# Examples:
python pipelines/pdf_processor.py document.pdf
python pipelines/pdf_processor.py document.pdf 1500
```

## Error Handling

### Common Issues and Solutions

**ImportError: No PDF library found**
```
Error: No PDF library found. Install 'pdfplumber' or 'pypdf2'
Solution: pip install pdfplumber PyPDF2
```

**FileNotFoundError: PDF file not found**
```
Error: PDF file not found: /path/to/document.pdf
Solution: Ensure the PDF path is correct and the file exists
```

**Warning: PDF appears to be OCR-based**
```
Warning: PDF document.pdf appears to be OCR-based. Text quality may be reduced.
Meaning: The PDF is scanned/image-based rather than text-based
Solution: Consider using OCR tools or improving PDF quality
```

## Performance Considerations

- **Memory**: Loading large PDFs (>100MB) may require significant memory
- **Processing Speed**: Extracting and chunking typically takes 1-5 seconds per PDF
- **Token Estimation**: Using tiktoken is more accurate but slightly slower than heuristics
- **Overlap**: Larger overlap values (>100 chars) increase chunk count

## Swedish Character Handling

The module correctly handles Swedish text:

```python
from pipelines.pdf_processor import extract_pdf_text

text = extract_pdf_text("swedish_document.pdf")

# All these are preserved:
# å - Riksåtgärder
# ä - Längre
# ö - Möjligheter

assert "å" in text or "ä" in text or "ö" in text
```

## Testing

Run the included tests:

```bash
python -m pytest tests/test_pdf_processor.py -v
```

Or manually test with the sample PDF:

```bash
python pipelines/pdf_processor.py tests/sample_juridik_document.pdf
```

## Architecture

The module is organized into several key components:

1. **PDFProcessor** - Main orchestrator class
   - Coordinates extraction and chunking
   - Manages configuration
   - Handles error cases

2. **TextCleaner** - Text cleaning utilities
   - Removes headers/footers
   - Detects section headers
   - Normalizes whitespace and characters

3. **TokenEstimator** - Token counting
   - Uses tiktoken for accuracy
   - Falls back to character-based heuristics
   - Configurable for different models

4. **Chunk** - Data structure
   - Represents a text chunk
   - Includes all relevant metadata
   - Serializable to dictionary/JSON

## Chunking Strategy

The module uses a two-level chunking strategy:

1. **Section-Level**: Text is first split by detected section headers
2. **Paragraph-Level**: Within each section, paragraphs are grouped into chunks
3. **Token Constraints**: Chunks are adjusted to fit within max_tokens
4. **Overlap**: 100 characters of overlap is added between consecutive chunks for context

This approach:
- Preserves document structure
- Maintains context through overlap
- Respects token limits for LLM compatibility
- Falls back gracefully for unstructured documents

## Development

To extend or modify the module:

```python
from pipelines.pdf_processor import PDFProcessor, Chunk, TextCleaner, TokenEstimator

class CustomPDFProcessor(PDFProcessor):
    def custom_chunking_strategy(self, text):
        # Implement custom chunking logic
        pass
```

## License

This module is part of the Juridik-AI project.

## References

- [pdfplumber Documentation](https://github.com/jsvine/pdfplumber)
- [PyPDF2 Documentation](https://github.com/py-pdf/PyPDF2)
- [tiktoken](https://github.com/openai/tiktoken)
