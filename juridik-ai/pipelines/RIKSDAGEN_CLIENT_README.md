# Riksdagen Client Module

A Python module for fetching and downloading documents from the Swedish Parliament's (Riksdagen) open data API.

## Overview

The `RiksdagenClient` module provides a high-level interface to the Riksdagen open data API at http://data.riksdagen.se. It supports:

- **Document searching** with filtering by type, year range, and search terms
- **Pagination support** for large result sets
- **Batch downloading** of documents with automatic retry
- **Rate limiting** to be respectful of the API
- **Resume capability** via checkpoints for long-running operations
- **Metadata export** to JSON
- **Comprehensive logging** and progress tracking
- **Error handling** and graceful degradation

## Installation

The module requires the `requests` library:

```bash
pip install requests
```

## Quick Start

### Basic Usage

```python
from pipelines.riksdagen_client import RiksdagenClient, DocumentType

# Initialize the client
client = RiksdagenClient()

# Search for documents
documents = client.search_documents(
    doktyp="prop",  # Propositions
    year_from=2023,
    year_to=2024
)

print(f"Found {len(documents)} propositions")

# Download documents
for doc in documents[:5]:  # Download first 5
    filepath = client.download_document(doc, file_format='pdf')
    print(f"Downloaded: {filepath}")
```

### Download All Documents of a Type

```python
from pipelines.riksdagen_client import RiksdagenClient

client = RiksdagenClient()

# Download all motions from 2024
total, downloaded, failed = client.download_all(
    doktyp="mot",
    year_range=(2024, 2024),
    file_format="pdf",
    resume=True  # Enable checkpoint resumption
)

print(f"Downloaded {downloaded}/{total} documents")
if failed:
    print(f"Failed: {failed}")
```

## Document Types

The module supports these document types from Riksdagen:

| Type | Code | Description |
|------|------|-------------|
| Proposition | `prop` | Government bill |
| Motion | `mot` | Parliamentary motion |
| SOU | `sou` | Government investigation report |
| Committee Report | `bet` | Committee report/statement |
| Interpellation | `ip` | Interpellation |
| Question | `fsk` | Question for written reply |
| Directive | `dir` | Directive to government agency |
| Department Memo | `ds` | Department memo |
| Written Statement | `skr` | Written statement |

Use the `DocumentType` enum for type safety:

```python
from pipelines.riksdagen_client import DocumentType

# These are equivalent
client.search_documents(doktyp="prop")
client.search_documents(doktyp=DocumentType.PROPOSITION.value)
```

## API Reference

### RiksdagenClient Class

#### Constructor

```python
RiksdagenClient(
    base_dir: str = "/home/dev/juridik-ai/data/riksdagen",
    rate_limit_delay: float = 0.5,
    timeout: int = 30,
    max_retries: int = 3,
)
```

**Parameters:**
- `base_dir`: Root directory for saving documents (organized by document type)
- `rate_limit_delay`: Delay between requests in seconds (default 0.5s)
- `timeout`: HTTP request timeout in seconds (default 30s)
- `max_retries`: Maximum retry attempts for failed requests (default 3)

#### search_documents()

Search for documents with filtering and pagination.

```python
documents = client.search_documents(
    doktyp: str,                          # Document type (required)
    year_from: int = 2020,                # Start year
    year_to: int = 2024,                  # End year
    search_term: Optional[str] = None,    # Optional search query
    page_size: int = 100,                 # Results per page (1-500)
    max_results: Optional[int] = None,    # Stop after N results
)
```

**Returns:** `List[Document]` - List of matching documents

**Example:**
```python
# Search for propositions about taxation
docs = client.search_documents(
    doktyp="prop",
    year_from=2023,
    year_to=2024,
    search_term="skatt",  # Swedish for "tax"
    page_size=200,
    max_results=500
)
```

#### get_document()

Fetch a single document by ID.

```python
document = client.get_document(doc_id: str)
```

**Parameters:**
- `doc_id`: Document ID (dokid)

**Returns:** `Optional[Document]` - Document object or None if not found

**Example:**
```python
doc = client.get_document("1984:1234")
if doc:
    print(doc.titel)  # Print document title
```

#### download_document()

Download a document's content.

```python
filepath = client.download_document(
    document: Document,
    file_format: str = 'pdf'
)
```

**Parameters:**
- `document`: Document object to download
- `file_format`: Format to download ('pdf', 'html', 'text')

**Returns:** `Optional[Path]` - Path to downloaded file or None if failed

**Example:**
```python
for doc in documents[:10]:
    filepath = client.download_document(doc, file_format='pdf')
    if filepath:
        print(f"Downloaded: {filepath}")
```

#### download_all()

Batch download all documents of a type with resume capability.

```python
total, downloaded, failed = client.download_all(
    doktyp: str,                          # Document type
    year_range: Tuple[int, int],          # (year_from, year_to)
    file_format: str = 'pdf',             # Format to download
    search_term: Optional[str] = None,    # Optional filter
    resume: bool = True,                  # Enable resumption
)
```

**Returns:** Tuple of `(total_docs, downloaded_count, failed_docs_list)`

**Example:**
```python
# Download all SOU reports from 2020-2024
total, downloaded, failed = client.download_all(
    doktyp="sou",
    year_range=(2020, 2024),
    file_format="pdf",
    resume=True  # Will resume from checkpoint if interrupted
)
print(f"Success: {downloaded}/{total}")
if failed:
    print(f"Failed documents: {failed}")
```

#### export_metadata()

Export document metadata to JSON file.

```python
filepath = client.export_metadata(
    documents: List[Document],
    output_file: Optional[str] = None
)
```

**Returns:** Path to JSON metadata file

**Example:**
```python
docs = client.search_documents(doktyp="prop", year_from=2024, year_to=2024)
metadata_file = client.export_metadata(docs)
# Output: /home/dev/juridik-ai/data/riksdagen/metadata_20240115_143022.json
```

#### get_statistics()

Get statistics about downloaded documents.

```python
stats = client.get_statistics()
```

**Returns:** Dictionary with stats

**Example:**
```python
stats = client.get_statistics()
print(f"Total documents: {stats['total_documents']}")
print(f"Total size: {stats['total_size_mb']} MB")
for doc_type, info in stats['document_types'].items():
    print(f"  {doc_type}: {info['count']} docs ({info['size_mb']} MB)")
```

### Document Class

Represents a document from Riksdagen.

**Attributes:**
- `dokid` (str): Document ID
- `titel` (str): Document title
- `subtitel` (Optional[str]): Subtitle
- `doktyp` (Optional[str]): Document type
- `publicerad` (Optional[str]): Publication date (ISO format)
- `rm` (Optional[str]): Riksmöte (parliament session)
- `beteckning` (Optional[str]): Document designation/reference
- `dokumentstatus` (Optional[str]): Status
- `url` (Optional[str]): Text URL
- `html_url` (Optional[str]): HTML URL
- `pdf_url` (Optional[str]): PDF URL
- `dokstat` (Optional[str]): Document status code

**Methods:**
- `to_dict()`: Convert document to dictionary

## Directory Structure

Downloaded documents are organized by type:

```
/home/dev/juridik-ai/data/riksdagen/
├── prop/                          # Propositions
│   ├── 1984:1234_Proposal_title.pdf
│   └── ...
├── mot/                           # Motions
│   ├── 1984:M1001_Motion_title.pdf
│   └── ...
├── sou/                           # SOU reports
│   ├── SOU 1984:50_Report_title.pdf
│   └── ...
├── bet/                           # Committee reports
├── metadata_20240115_143022.json  # Exported metadata
├── session.log                    # Activity log
└── .checkpoint_download_prop_2024_2024.json  # Resume checkpoint
```

## Resume Capability

When calling `download_all()` with `resume=True`, the client:

1. Creates a checkpoint file after every 10 downloads
2. Saves checkpoint with list of successful and failed documents
3. On restart, checks for checkpoint and skips already-downloaded files
4. Final checkpoint is marked as `completed: true`

**Checkpoint file format:**
```json
{
  "downloaded": ["1984:1234", "1984:1235", ...],
  "failed": ["1984:1240"],
  "progress": 45,
  "total": 100,
  "timestamp": "2024-01-15T14:30:22.123456",
  "completed": false
}
```

**Resume automatically:**
```python
# First run: interrupted after 50 documents
client.download_all(doktyp="prop", year_range=(2023, 2024))

# Second run: automatically resumes from checkpoint
client.download_all(doktyp="prop", year_range=(2023, 2024), resume=True)
```

## Rate Limiting

The client is respectful to the Riksdagen API:

- **Default rate limit**: 0.5 seconds between requests (2 req/sec)
- **Configurable**: Pass `rate_limit_delay` to constructor
- **Automatic retries**: Failed requests retry with exponential backoff
- **Session log**: All activities logged to `session.log`

```python
# More aggressive rate limiting (1 request per second)
client = RiksdagenClient(rate_limit_delay=1.0)

# Faster rate (4 requests per second) - use with caution
client = RiksdagenClient(rate_limit_delay=0.25)
```

## Error Handling

The module handles errors gracefully:

```python
from pipelines.riksdagen_client import RiksdagenClient

client = RiksdagenClient()

try:
    docs = client.search_documents(doktyp="prop", year_from=2023, year_to=2024)
except Exception as e:
    print(f"Search failed: {e}")

# Download with error handling
for doc in documents:
    try:
        filepath = client.download_document(doc)
    except Exception as e:
        print(f"Failed to download {doc.dokid}: {e}")
        continue
```

## Logging

The module uses Python's standard logging module:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or configure specific logger
logger = logging.getLogger('pipelines.riksdagen_client')
logger.setLevel(logging.DEBUG)
```

**Log levels:**
- `INFO`: Normal operation (searches, downloads, progress)
- `WARNING`: Non-fatal issues (skipped documents, missing data)
- `ERROR`: Failed operations (network errors, download failures)
- `DEBUG`: Detailed progress (rate limiting, pagination)

## Common Patterns

### Search and Download in Batch

```python
from pipelines.riksdagen_client import RiksdagenClient

client = RiksdagenClient()

# Download all propositions from 2024
total, downloaded, failed = client.download_all(
    doktyp="prop",
    year_range=(2024, 2024),
    file_format="pdf"
)

print(f"Downloaded {downloaded}/{total} propositions")
```

### Search and Export Metadata

```python
# Search for specific documents
docs = client.search_documents(
    doktyp="bet",  # Committee reports
    year_from=2023,
    year_to=2024,
    search_term="arbete"  # About work/employment
)

# Export metadata for processing
metadata_file = client.export_metadata(docs)
print(f"Metadata saved to: {metadata_file}")
```

### Fetch Single Document

```python
# Get a specific document
doc = client.get_document("1984:1234")

if doc:
    print(f"Title: {doc.titel}")
    print(f"Status: {doc.dokumentstatus}")

    # Download it
    filepath = client.download_document(doc, file_format='pdf')
    print(f"Downloaded to: {filepath}")
```

### Download Multiple Formats

```python
doc = client.get_document("1984:1234")

if doc:
    # Download in multiple formats
    for fmt in ['pdf', 'html', 'text']:
        filepath = client.download_document(doc, file_format=fmt)
        if filepath:
            print(f"Downloaded ({fmt}): {filepath}")
```

## API Limits and Notes

- **Page size**: Maximum 500 documents per page
- **Rate limit**: Respect 0.5+ second delays (default behavior)
- **Timeout**: 30 seconds per request (configurable)
- **Retry**: Automatic retry with exponential backoff for 429/50x errors
- **Sessions**: Use kontinuous sessions for multiple requests (built-in)

## Troubleshooting

### "No documents found"

```python
# Check if year range is correct
docs = client.search_documents(
    doktyp="prop",
    year_from=2020,  # Try earlier years
    year_to=2024
)

# Try without search term
docs = client.search_documents(
    doktyp="prop",
    year_from=2024,
    year_to=2024
)
```

### Download fails with timeout

```python
# Increase timeout
client = RiksdagenClient(timeout=60)

# Or use slower rate limiting
client = RiksdagenClient(rate_limit_delay=2.0)
```

### Resume not working

Check checkpoint files:
```bash
ls -la /home/dev/juridik-ai/data/riksdagen/.checkpoint_*.json
```

Delete checkpoint to start fresh:
```bash
rm /home/dev/juridik-ai/data/riksdagen/.checkpoint_download_prop_2024_2024.json
```

## Performance Tips

1. **Use `max_results` for testing**: Set a limit before doing large downloads
2. **Adjust page size**: Larger pages (up to 500) mean fewer requests
3. **Rate limiting**: Decrease for reliability, increase for speed (cautiously)
4. **Metadata export**: Useful for batch processing
5. **Resume capability**: Essential for large downloads over unreliable connections

## References

- Riksdagen API: http://data.riksdagen.se
- Document types and codes: http://data.riksdagen.se/dokument/
- Session years: http://data.riksdagen.se/dokumentlista/?rm=2023/24&sz=1&utformat=json
