# Implementation Roadmap - Constitutional AI RAG System

**Baserat på**: Research från `/home/agentic-dev/Documents/RAG-IMPLEMENTATIONS`  
**Datum**: 2025-01-15  
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

#### 1.2 Byt Modell till Mistral-Nemo 12B Q5_K_M 🔴 **HÖG PRIORITET**
- Enligt research: GPT-SW3 är föråldrad, Mistral-Nemo optimal för 12GB
- Konfigurera llama-server med KV-cache kvantisering
- **Effort**: 1 dag | **Impact**: Mycket hög

#### 1.3 Aktivera KV-Cache Kvantisering (Q8_0) 🔴 **HÖG PRIORITET**
- "Gratis uppgradering" som halverar minnesanvändning
- Lägg till `-ctk q8_0 -ctv q8_0` i llama-server
- **Effort**: 1 timme | **Impact**: Hög

#### 1.4 Aktivera Spekulativ Avkodning 🟡 **MEDIUM PRIORITET**
- 1.5x-2.5x hastighetsökning med 0.5B draft-modell
- **Effort**: 2-3 timmar | **Impact**: Hög

---

### FASE 2: Arkitekturförbättringar (Hög Impact/Medel Insats) - 2-3 veckor

#### 2.1 Implementera BGE-M3 för Embeddings 🔴 **HÖG PRIORITET**
- BGE-M3 överlägsen för svensk text med hybrid-sökning
- Re-indexera ChromaDB collections
- **Effort**: 2-3 dagar | **Impact**: Mycket hög

#### 2.2 Implementera Corrective RAG (CRAG) med LangGraph 🔴 **HÖG PRIORITET**
- Minskar hallucinationer med 50% genom självkritisk loop
- Du har redan CRAG-grading! Förbättra till full LangGraph
- **Effort**: 3-5 dagar | **Impact**: Mycket hög

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

## 📊 Jämförelse: Nuvarande vs. Planerat

| Komponent | Nuvarande | Planerat |
|-----------|-----------|----------|
| LLM | Mistral 14B | Mistral-Nemo 12B Q5_K_M |
| Embedding | sentence-BERT | BGE-M3 |
| RAG | Linjär | CRAG + LangGraph |
| KV-Cache | FP16 | Q8_0 |
| Avkodning | Standard | Spekulativ |

---

**Nästa steg**: Börja med refactoring, sedan byt modell!
