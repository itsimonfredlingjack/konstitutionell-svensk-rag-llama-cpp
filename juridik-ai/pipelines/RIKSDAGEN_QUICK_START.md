# Riksdagen Client - Quick Start Guide

## Installation

Ensure `requests` library is installed:

```bash
pip install requests
```

## Basic Usage

### 1. Search for Documents

```python
from pipelines.riksdagen_client import RiksdagenClient

client = RiksdagenClient()

# Search for propositions from 2024
documents = client.search_documents(
    doktyp="prop",      # Document type
    year_from=2024,     # From year
    year_to=2024,       # To year
    max_results=10      # Limit results
)

print(f"Found {len(documents)} documents")
for doc in documents:
    print(f"  - {doc.titel} ({doc.dokid})")
```

### 2. Download Documents

```python
# Download a single document
for doc in documents[:5]:
    filepath = client.download_document(doc, file_format='pdf')
    print(f"Downloaded: {filepath}")
```

### 3. Batch Download with Resume

```python
# Download all motions from 2024 (resumes on interruption)
total, downloaded, failed = client.download_all(
    doktyp="mot",
    year_range=(2024, 2024),
    file_format="pdf",
    resume=True
)

print(f"Result: {downloaded}/{total} downloaded, {len(failed)} failed")
```

## Document Types

| Code | Name |
|------|------|
| `prop` | Proposition (Government bill) |
| `mot` | Motion (Parliamentary motion) |
| `sou` | SOU (Government investigation) |
| `bet` | Committee Report |
| `ip` | Interpellation |
| `fsk` | Question for written reply |
| `dir` | Directive |
| `ds` | Department memo |
| `skr` | Written statement |

## Common Tasks

### Search with Filter

```python
# Search for documents about health ("hälsa")
docs = client.search_documents(
    doktyp="mot",
    year_from=2023,
    year_to=2024,
    search_term="hälsa"
)
```

### Get Single Document

```python
doc = client.get_document("1984:1234")
if doc:
    print(f"Title: {doc.titel}")
    print(f"Status: {doc.dokumentstatus}")
```

### Export Metadata

```python
# Search documents
docs = client.search_documents(
    doktyp="bet",
    year_from=2024,
    year_to=2024
)

# Export metadata to JSON
metadata_file = client.export_metadata(docs)
print(f"Metadata saved to: {metadata_file}")
```

### Get Statistics

```python
stats = client.get_statistics()
print(f"Total documents: {stats['total_documents']}")
print(f"Total size: {stats['total_size_mb']} MB")

for doc_type, info in stats['document_types'].items():
    print(f"  {doc_type}: {info['count']} docs, {info['size_mb']} MB")
```

## Configuration

```python
# Custom rate limiting (slower = safer)
client = RiksdagenClient(
    base_dir="/path/to/docs",      # Where to save documents
    rate_limit_delay=1.0,            # 1 second between requests
    timeout=30,                      # Request timeout
    max_retries=3                    # Retry failed requests
)
```

## Directory Structure

Downloaded files are organized by type:

```
/home/dev/juridik-ai/data/riksdagen/
├── prop/              # Propositions
├── mot/               # Motions
├── sou/               # SOU reports
├── bet/               # Committee reports
├── metadata_*.json    # Exported metadata
└── session.log        # Activity log
```

## Resuming Downloads

If a batch download is interrupted:

```bash
# Checkpoint is automatically saved
# Run the same command to resume
python your_script.py
```

The client automatically skips already-downloaded files and failed documents.

## Error Handling

```python
try:
    docs = client.search_documents(
        doktyp="prop",
        year_from=2024,
        year_to=2024
    )
except Exception as e:
    print(f"Search failed: {e}")

# Or download with per-document error handling
for doc in documents:
    try:
        filepath = client.download_document(doc)
    except Exception as e:
        print(f"Failed: {doc.dokid} - {e}")
        continue
```

## Run Examples

```bash
# Run all examples
python examples/riksdagen_examples.py

# Run specific example
python examples/riksdagen_examples.py 1  # Basic search
python examples/riksdagen_examples.py 2  # Search with filter
python examples/riksdagen_examples.py 3  # Get single document
python examples/riksdagen_examples.py 4  # Download single
python examples/riksdagen_examples.py 5  # Batch download
python examples/riksdagen_examples.py 6  # Export metadata
python examples/riksdagen_examples.py 7  # Statistics
python examples/riksdagen_examples.py 8  # Multiple formats
python examples/riksdagen_examples.py 9  # All document types
python examples/riksdagen_examples.py 10 # Resume capability
```

## Run Tests

```bash
# Run all tests
pytest tests/test_riksdagen_client.py -v

# Run specific test
pytest tests/test_riksdagen_client.py::TestRiksdagenClientInit -v

# Run with coverage
pytest tests/test_riksdagen_client.py --cov=pipelines.riksdagen_client
```

## Troubleshooting

### No documents found
- Check document type is correct
- Try different year range
- Remove search term filter

### Download fails
- Increase timeout: `RiksdagenClient(timeout=60)`
- Reduce rate limit: `RiksdagenClient(rate_limit_delay=2.0)`
- Check disk space

### Resume not working
- Delete checkpoint: `rm /home/dev/juridik-ai/data/riksdagen/.checkpoint_*.json`
- Or start fresh with `resume=False`

## API Limits

- **Max page size**: 500 documents
- **Default rate limit**: 0.5 seconds (2 requests/sec)
- **Timeout**: 30 seconds per request
- **Auto-retry**: 429, 500, 502, 503, 504 errors

Be respectful to the API - don't reduce rate_limit_delay below 0.5 seconds without good reason.

## More Information

- Full documentation: See `RIKSDAGEN_CLIENT_README.md`
- API documentation: http://data.riksdagen.se
- Examples: See `examples/riksdagen_examples.py`
- Tests: See `tests/test_riksdagen_client.py`
