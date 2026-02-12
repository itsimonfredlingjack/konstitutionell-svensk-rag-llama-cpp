# Implementation Roadmap - Constitutional AI RAG System

**Baserat på**: Research från `/home/agentic-dev/Documents/RAG-IMPLEMENTATIONS`
**Datum**: 2026-02-07
**Mål**: Optimera RAG-system för 12GB VRAM med konstitutionell AI-principer

---

## 🎯 Översikt

Din research identifierar en omfattande plan för att transformera det nuvarande RAG-systemet till en toppmodern, konstitutionell AI-lösning.

---

## 📋 Prioriterad Handlingsplan

### FASE 1: Omedelbar Optimering (Hög Impact/Låg Insats) - 1 vecka

#### 1.1 Slutför Refactoring av OrchestratorService 🔴 **PÅGÅENDE**
- Extract `_parse_structured_output()` (~155 rader)
- Extract `_apply_critic_revisions()` (~146 rader)  
- Extract `_build_metrics()` (~80 rader)
- **Mål**: `process_query()` <100 rader
- **Effort**: 2-3 dagar

#### 1.2 ✅ Byt Modell till Mistral-Nemo 12B Q5_K_M **DONE**
- ✅ Mistral-Nemo-Instruct-2407-Q5_K_M.gguf aktiverad via llama-server
- ✅ Konfigurerad med llama-server på port 8080
- **Status**: Implementerad och i produktion

#### 1.3 Aktivera KV-Cache Kvantisering (Q8_0) 🔴 **HÖG PRIORITET**
- "Gratis uppgradering" som halverar minnesanvändning
- Lägg till `-ctk q8_0 -ctv q8_0` i llama-server
- **Effort**: 1 timme | **Impact**: Hög

#### 1.4 Aktivera Spekulativ Avkodning 🟡 **MEDIUM PRIORITET**
- 1.5x-2.5x hastighetsökning med 0.5B draft-modell
- **Effort**: 2-3 timmar | **Impact**: Hög

---

### FASE 2: Arkitekturförbättringar (Hög Impact/Medel Insats) - 2-3 veckor

#### 2.1 ✅ Implementera Jina v3 för Embeddings **DONE**
- ✅ jinaai/jina-embeddings-v3 implementerad (1024 dimensions)
- ✅ BAAI/bge-reranker-v2-m3 aktiverad
- ✅ ChromaDB collections re-indexerade med `_jina_v3_1024` suffix
- ✅ 1.37M+ documents indexerade
- **Status**: I produktion

#### 2.2 ✅ Implementera Corrective RAG (CRAG) **DONE**
- ✅ CRAG enabled i produktion
- ✅ Self-reflection + grading active
- ✅ GraderService + CriticService implementerade
- 🟡 LangGraph integration pågående
- **Status**: Core CRAG i produktion, LangGraph nästa steg

#### 2.3 Dela upp OrchestratorService 🟡 **MEDIUM PRIORITET**
- Skapa QueryOrchestrator, GenerationOrchestrator, ValidationOrchestrator
- **Effort**: 3-5 dagar | **Impact**: Hög

#### 2.4 Implementera Contextual Retrieval 🟡 **MEDIUM PRIORITET**
- Minskar retrieval-fel med 50% genom kontextsammanfattningar
- **Effort**: 3-4 dagar | **Impact**: Hög

---

## 🎯 Konkret Nästa Steg (Denna Vecka)

1. **Slutför Refactoring** (2-3 dagar)
2. **Byt Modell till Mistral-Nemo 12B** (1 dag)
3. **Aktivera KV-cache kvantisering** (1 timme)
4. **Aktivera spekulativ avkodning** (2-3 timmar)

---

## 📊 Jämförelse: Ursprunglig vs. Nuvarande

| Komponent | Ursprunglig | Nuvarande (2026-02-07) |
|-----------|-------------|------------------------|
| LLM | gpt-sw3 | ✅ Mistral-Nemo-Instruct-2407-Q5_K_M.gguf |
| Embedding | sentence-BERT | ✅ jinaai/jina-embeddings-v3 (1024d) |
| Reranker | None | ✅ BAAI/bge-reranker-v2-m3 |
| Vector DB | Qdrant | ✅ ChromaDB |
| RAG | Linjär | ✅ CRAG (enabled) |
| Port | 8000 | ✅ 8900 |
| Doc Count | 521K | ✅ 1.37M+ |
| LLM Runtime | Ollama primary | ✅ llama-server (Ollama fallback only) |
| KV-Cache | FP16 | 🟡 Q8_0 (nästa steg) |
| Avkodning | Standard | 🟡 Spekulativ (nästa steg) |

---

## ✅ Genomförda Förbättringar (2026-02-07)

1. ✅ **Mistral-Nemo-Instruct-2407-Q5_K_M.gguf** - Optimal 12B-modell aktiverad
2. ✅ **jinaai/jina-embeddings-v3** embeddings - 1024 dimensions
3. ✅ **BAAI/bge-reranker-v2-m3** - Reranking aktiverad
4. ✅ **ChromaDB** - Migrerad från Qdrant
5. ✅ **CRAG enabled** - Self-reflection + grading
6. ✅ **1.37M+ documents** - Korpus utökad (538K legal/gov + 829K DiVA)
7. ✅ **Port 8900** - Backend i produktion
8. ✅ **llama-server primary** - Ollama endast fallback

---

**Nästa steg**: KV-cache kvantisering (Q8_0) + Spekulativ avkodning för ytterligare hastighetsökning!
