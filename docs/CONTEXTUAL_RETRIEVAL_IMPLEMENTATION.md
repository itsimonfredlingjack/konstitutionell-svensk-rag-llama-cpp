# Contextual Retrieval Implementation - Steg 2.1

**Status**: ✅ **IMPLEMENTERAD**

---

## ✅ Vad Är Skapat

### 1. ContextualIngestor (`indexers/contextual_ingestor.py`)
**Klass**: `ContextualIngestor`

**Funktionalitet**:
- ✅ Tar emot råtext från dokument
- ✅ Delar upp i chunks (~500 tokens)
- ✅ Genererar kontextsammanfattning för varje chunk via LLM
- ✅ Prependar sammanfattningen till chunken: `[KONTEXT] {summary}\n\n[TEXT] {original_chunk}`
- ✅ Embeddar den berikade texten med BGE-M3
- ✅ Sparar originaltexten i metadata (`page_content`)

**Metoder**:
- `process_document()`: Processerar dokument och genererar contextual chunks
- `_generate_context_summary()`: Anropar LLM för kontextsammanfattning
- `embed_chunks()`: Embeddar chunks med BGE-M3
- `process_and_embed()`: Komplett pipeline

### 2. ContextualChromaDBIndexer (`indexers/contextual_chromadb_indexer.py`)
**Klass**: `ContextualChromaDBIndexer`

**Funktionalitet**:
- ✅ Integrerar ContextualIngestor med ChromaDB
- ✅ Indexerar dokument med contextual retrieval
- ✅ Sparar enriched text för embedding
- ✅ Sparar original text i metadata (`page_content`) för visning

**Metoder**:
- `index_document()`: Indexerar ett dokument
- `index_documents_batch()`: Indexerar flera dokument
- `get_collection_stats()`: Hämtar statistik

---

## 📋 Användning

### Exempel 1: Indexera ett dokument

```python
from contextual_chromadb_indexer import ContextualChromaDBIndexer

indexer = ContextualChromaDBIndexer(
    collection_name="swedish_gov_docs_bge_m3_1024"
)

result = await indexer.index_document(
    full_text="Hela dokumenttexten här...",
    document_title="GDPR-lagen",
    document_id="gdpr_2024",
    document_metadata={"source": "europa.eu", "date": "2024-01-01"}
)

print(f"Indexed {result['chunks_indexed']} chunks")
```

### Exempel 2: Batch-indexering

```python
documents = [
    {
        "full_text": "...",
        "document_title": "Dokument 1",
        "document_id": "doc1",
        "metadata": {"source": "myndighet"}
    },
    {
        "full_text": "...",
        "document_title": "Dokument 2",
        "document_id": "doc2",
    }
]

result = await indexer.index_documents_batch(documents)
print(f"Indexed {result['total_chunks_indexed']} chunks from {result['documents_successful']} documents")
```

---

## 🔧 Konfiguration

### LLM för Kontextgenerering
- **Default**: Qwen2.5-0.5B-Instruct-Q8_0.gguf (lättviktig modell)
- **Temperature**: 0.3 (låg för faktabaserade sammanfattningar)
- **Max tokens**: 150 (korta sammanfattningar)

### Chunking
- **Chunk size**: 500 tokens (default)
- **Overlap**: 50 tokens (default)
- **Konvertering**: ~4 chars/token för svensk text

### Embedding
- **Model**: BGE-M3 (BAAI/bge-m3)
- **Dimension**: 1024
- **Device**: CPU (för att spara VRAM för LLM)

---

## 📊 Dataformat i ChromaDB

### Dokument Field
Stores enriched text (för embedding):
```
[KONTEXT] Detta avsnitt rör semesterlönegrundande frånvaro i Semesterlagen, kapitel 3.

[TEXT] Enligt 3 kap. 1 § ska semesterlön betalas...
```

### Metadata Field
Stores original text (för visning):
```json
{
  "page_content": "Enligt 3 kap. 1 § ska semesterlön betalas...",
  "context_summary": "Detta avsnitt rör semesterlönegrundande frånvaro i Semesterlagen, kapitel 3.",
  "document_id": "semesterlagen_2024",
  "document_title": "Semesterlagen",
  "chunk_index": 0,
  "total_chunks": 15
}
```

---

## ⚠️ Viktiga Noteringar

### 1. Retrieval Service Kompatibilitet
Retrieval service behöver uppdateras för att använda `page_content` från metadata när den returnerar resultat, istället för den berikade texten.

**Nuvarande beteende**: Returnerar `documents[0][i]` (berikad text)
**Önskat beteende**: Returnerar `metadatas[0][i].get("page_content", documents[0][i])` (original text)

### 2. Re-indexering Krävs
För att använda contextual retrieval måste befintliga dokument re-indexeras med den nya pipelinen.

### 3. LLM Tillgänglighet
ContextualIngestor kräver att llama-server körs på port 8080 för att generera kontextsammanfattningar.

---

## 🎯 Nästa Steg

1. **Uppdatera Retrieval Service**: Se till att den använder `page_content` från metadata
2. **Testa på små dataset**: Testa contextual retrieval på ett litet dokument
3. **Re-indexera**: Planera re-indexering av befintliga dokument
4. **Mät förbättring**: Jämför retrieval-kvalitet före/efter
