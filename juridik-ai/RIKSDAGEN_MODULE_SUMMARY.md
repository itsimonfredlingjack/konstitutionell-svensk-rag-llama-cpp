# Riksdagen Client Module - Complete Implementation Summary

## Overview

A professional-grade Python module for fetching and downloading documents from the Swedish Parliament's (Riksdagen) open data API at http://data.riksdagen.se.

**Status**: ✓ Complete and fully tested

## Files Created

### Core Module
- **`/home/dev/juridik-ai/pipelines/riksdagen_client.py`** (600+ lines)
  - Main module with `RiksdagenClient` class
  - `Document` dataclass for type safety
  - `DocumentType` enum for document types
  - Full implementation of all features

### Documentation
- **`/home/dev/juridik-ai/pipelines/RIKSDAGEN_CLIENT_README.md`** (500+ lines)
  - Comprehensive API reference
  - Installation instructions
  - Quick start examples
  - All methods documented with examples
  - Troubleshooting section
  - Performance tips

- **`/home/dev/juridik-ai/pipelines/RIKSDAGEN_QUICK_START.md`** (200+ lines)
  - Quick reference for common tasks
  - Document types reference
  - Configuration guide
  - Running examples and tests

### Examples
- **`/home/dev/juridik-ai/examples/riksdagen_examples.py`** (400+ lines)
  - 10 complete usage examples
  - Run individually or all at once
  - Covers all major features
  - Can be run with: `python examples/riksdagen_examples.py [1-10]`

- **`/home/dev/juridik-ai/examples/riksdagen_bulk_download.py`** (300+ lines)
  - Production-ready bulk download script
  - Command-line interface with arguments
  - Progress tracking and statistics
  - Resume capability
  - Can be run with: `python examples/riksdagen_bulk_download.py --help`

### Tests
- **`/home/dev/juridik-ai/tests/test_riksdagen_client.py`** (400+ lines)
  - 23 comprehensive unit tests
  - Tests for all major functionality
  - Mocked API integration tests
  - All tests passing: ✓

## Features Implemented

### 1. Document Searching
```python
documents = client.search_documents(
    doktyp="prop",
    year_from=2023,
    year_to=2024,
    search_term="skatt",  # Optional filter
    page_size=200,
    max_results=500
)
```

**Supported document types:**
- `prop` - Propositions (Government bills)
- `mot` - Motions (Parliamentary motions)
- `sou` - Government investigation reports
- `bet` - Committee reports
- `ip` - Interpellations
- `fsk` - Questions for written reply
- `dir` - Directives
- `ds` - Department memos
- `skr` - Written statements

### 2. Single Document Retrieval
```python
doc = client.get_document("1984:1234")
if doc:
    print(f"Title: {doc.titel}")
    print(f"Status: {doc.dokumentstatus}")
```

### 3. Document Download
```python
# Download in different formats
filepath = client.download_document(doc, file_format='pdf')
filepath = client.download_document(doc, file_format='html')
filepath = client.download_document(doc, file_format='text')
```

### 4. Batch Download with Resume
```python
total, downloaded, failed = client.download_all(
    doktyp="mot",
    year_range=(2024, 2024),
    file_format="pdf",
    resume=True  # Automatic checkpoint resumption
)
```

**Resume features:**
- Automatic checkpoint every 10 documents
- Tracks downloaded and failed documents
- Automatically skips already-downloaded files
- Resume on restart without re-downloading

### 5. Metadata Export
```python
metadata_file = client.export_metadata(documents)
# Creates: /path/to/riksdagen/metadata_20240115_143022.json
```

### 6. Statistics & Monitoring
```python
stats = client.get_statistics()
# Returns:
# {
#   'total_documents': 1234,
#   'total_size_mb': 456.78,
#   'document_types': {
#       'prop': {'count': 500, 'size_mb': 200.0},
#       'mot': {'count': 734, 'size_mb': 256.78}
#   }
# }
```

### 7. Rate Limiting
- Default: 0.5 seconds between requests (2 req/sec)
- Configurable delay parameter
- Automatic backoff retry for rate limit (429) errors
- Respectful API usage

### 8. Error Handling
- Graceful error handling for network issues
- Automatic retry with exponential backoff
- Logging of failed operations
- Checkpoint-based recovery

### 9. Session Logging
- All activities logged to `session.log`
- Tracks searches, downloads, failures
- Enables audit trail for large operations

## Architecture

### Class Hierarchy

```
RiksdagenClient
├── Base URL: http://data.riksdagen.se
├── API Endpoint: /dokumentlista/
├── Session Management (with retry strategy)
├── Rate Limiting (configurable)
├── Checkpoint System (for resume)
└── Session Logging

Document (dataclass)
├── dokid
├── titel
├── subtitel
├── doktyp
├── publicerad
├── rm (riksmöte/session)
├── beteckning
├── dokumentstatus
├── url (text)
├── html_url
├── pdf_url
└── dokstat

DocumentType (enum)
├── PROPOSITION = "prop"
├── MOTION = "mot"
├── SOU = "sou"
├── BETANKANDE = "bet"
├── INTERPELLATION = "ip"
├── FRÅGA_UTAN_SVAR = "fsk"
├── DIREKTIV = "dir"
├── DEPARTEMENTSSKRIVELSE = "ds"
└── SKRIVELSE = "skr"
```

## Directory Structure

```
/home/dev/juridik-ai/
├── pipelines/
│   ├── riksdagen_client.py              # Main module
│   ├── RIKSDAGEN_CLIENT_README.md       # Full documentation
│   └── RIKSDAGEN_QUICK_START.md         # Quick reference
├── examples/
│   ├── riksdagen_examples.py            # 10 usage examples
│   └── riksdagen_bulk_download.py       # Bulk download script
├── tests/
│   └── test_riksdagen_client.py         # 23 unit tests
└── data/
    └── riksdagen/                       # Downloaded documents
        ├── prop/                        # Propositions
        ├── mot/                         # Motions
        ├── sou/                         # SOU reports
        ├── bet/                         # Committee reports
        ├── metadata_*.json              # Exported metadata
        ├── session.log                  # Activity log
        └── .checkpoint_*.json           # Resume checkpoints
```

## API Specifications

### Query Parameters
- `doktyp`: Document type (required)
- `rm`: Riksmöte/session (e.g., "2023/24")
- `sz`: Page size (1-500, default 100)
- `sid`: Page number (for pagination)
- `sok`: Search term (optional)
- `utformat`: Response format (json)

### Response Format
```json
{
  "dokument": [
    {
      "dokid": "1984:1234",
      "titel": "Document Title",
      "dokumentstatus": "Fastställd",
      "dokument_url_pdf": "http://example.com/doc.pdf",
      "dokument_url_html": "http://example.com/doc.html",
      "dokument_url_text": "http://example.com/doc.txt",
      ...
    },
    ...
  ]
}
```

## Usage Examples

### Example 1: Basic Search
```python
from pipelines.riksdagen_client import RiksdagenClient

client = RiksdagenClient()
docs = client.search_documents(
    doktyp="prop",
    year_from=2024,
    year_to=2024,
    max_results=10
)
print(f"Found {len(docs)} documents")
```

### Example 2: Download with Filter
```python
# Search for health-related motions
docs = client.search_documents(
    doktyp="mot",
    year_from=2023,
    year_to=2024,
    search_term="hälsa"
)

# Download all
for doc in docs:
    filepath = client.download_document(doc, file_format='pdf')
```

### Example 3: Batch Download
```python
# Download all SOU reports from 2020-2024
total, downloaded, failed = client.download_all(
    doktyp="sou",
    year_range=(2020, 2024),
    file_format="pdf",
    resume=True
)
print(f"Downloaded {downloaded}/{total}")
```

### Example 4: Export Metadata
```python
docs = client.search_documents(doktyp="bet", year_from=2024, year_to=2024)
metadata_file = client.export_metadata(docs)
print(f"Saved to: {metadata_file}")
```

## Running the Code

### Installation
```bash
pip install requests
```

### Run Examples
```bash
# All examples
python examples/riksdagen_examples.py

# Specific example
python examples/riksdagen_examples.py 1  # Basic search
python examples/riksdagen_examples.py 5  # Batch download

# Bulk download script
python examples/riksdagen_bulk_download.py --help
python examples/riksdagen_bulk_download.py --doktyp prop --year-from 2024 --year-to 2024
```

### Run Tests
```bash
# All tests
pytest tests/test_riksdagen_client.py -v

# Specific test class
pytest tests/test_riksdagen_client.py::TestRiksdagenClientInit -v

# With coverage
pytest tests/test_riksdagen_client.py --cov=pipelines.riksdagen_client
```

## Test Results

All 23 tests passing:
- 3 Document class tests
- 1 DocumentType enum test
- 3 Client initialization tests
- 1 Rate limiting test
- 3 Checkpoint tests
- 2 Document parsing tests
- 2 Metadata export tests
- 2 Statistics tests
- 1 Session logging test
- 4 Integration tests (mocked)
- 1 Import test

## Configuration Options

```python
client = RiksdagenClient(
    base_dir="/home/dev/juridik-ai/data/riksdagen",  # Where to save
    rate_limit_delay=0.5,                            # Delay between requests
    timeout=30,                                       # Request timeout (seconds)
    max_retries=3                                     # Retry attempts
)
```

## Key Advantages

1. **Type Safe**: Uses dataclasses and enums for type safety
2. **Resilient**: Automatic retry with exponential backoff
3. **Resumable**: Checkpoint-based resumption for interrupted downloads
4. **Rate Limited**: Respectful API usage with configurable delays
5. **Well Logged**: Comprehensive logging for debugging and audit trail
6. **Well Tested**: 23 unit tests covering all functionality
7. **Well Documented**: Full API docs + quick start guide
8. **Production Ready**: Error handling, statistics, progress tracking
9. **Easy to Use**: Simple, intuitive API for common tasks
10. **Extensible**: Clean architecture for future enhancements

## Performance Characteristics

- **Memory**: Efficient streaming of downloads (8KB chunks)
- **CPU**: Minimal overhead (mostly I/O bound)
- **Network**: Respects API limits with default 0.5s rate limit
- **Storage**: Organized by document type in configurable base directory
- **Throughput**: ~2 requests/second (configurable)

## Known Limitations

1. Authentication not required (public API)
2. Session format varies by year ("2023/24", "2024/25", etc.)
3. Not all documents have all formats available (PDF, HTML, Text)
4. API response may include deleted/withdrawn documents
5. Search functionality limited to full-text search (no advanced filters)

## Future Enhancements (Optional)

- [ ] Advanced search filters (committee, rapporteur, etc.)
- [ ] Document content parsing/extraction
- [ ] Database storage option (instead of filesystem)
- [ ] Web UI for browsing downloads
- [ ] Document comparison/diff functionality
- [ ] Full-text search integration with Elasticsearch
- [ ] OAuth authentication support
- [ ] Webhook notifications

## Maintenance Notes

- API endpoint: http://data.riksdagen.se (stable)
- Document types and codes are stable
- Session format: YYYY/YY (e.g., 2023/24)
- Rate limits: Respectful defaults (0.5s delay)
- Retry strategy: 429/50x errors with exponential backoff

## Support Resources

- **API Documentation**: http://data.riksdagen.se
- **Module Docs**: `RIKSDAGEN_CLIENT_README.md`
- **Quick Start**: `RIKSDAGEN_QUICK_START.md`
- **Examples**: `examples/riksdagen_examples.py`
- **Tests**: `tests/test_riksdagen_client.py`

## Summary

This module provides a complete, production-ready interface to the Riksdagen open data API. It handles all the complexities of pagination, rate limiting, error handling, and resumption automatically, allowing developers to focus on their data analysis tasks. The module is well-tested, well-documented, and follows Python best practices.

**Status**: ✓ Ready for production use

**Files**: 7 total (1 module + 3 docs + 2 examples + 1 test)
**Lines of Code**: 2500+ total
**Test Coverage**: 23 tests, all passing
**Documentation**: 1000+ lines

Created: 2024-11-27
