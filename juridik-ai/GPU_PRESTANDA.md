# GPU Prestanda-analys för RTX 2060 (6 GB VRAM)

## Din GPU:
- **RTX 2060** med **6 GB VRAM**
- **Prestanda**: Bra för 4-5 GB modeller, tight för 6+ GB modeller

## Praktisk prestanda:

### ✅ **Bra prestanda** (körs på GPU, snabbt):
- **Gemma3:4b** (3.3 GB fil) → ~4-5 GB VRAM
  - **Prestanda**: ⭐⭐⭐⭐⭐ Mycket bra
  - **Körs på**: GPU (helt)
  - **Hastighet**: Snabb

- **DeepSeek R1:1.5b** (1.1 GB fil) → ~2 GB VRAM
  - **Prestanda**: ⭐⭐⭐⭐⭐ Mycket snabb
  - **Körs på**: GPU (helt)
  - **Hastighet**: Mycket snabb

### ⚠️ **Okej prestanda** (körs delvis på GPU/CPU):
- **DeepSeek R1:7b** (4.7 GB fil) → ~6-7 GB VRAM
  - **Prestanda**: ⭐⭐⭐ Okej (kan vara tight)
  - **Körs på**: GPU (delvis) + CPU (delvis)
  - **Hastighet**: Okej, kan vara långsamt ibland

- **DeepSeek R1:8b** (5.2 GB fil) → ~6-7 GB VRAM
  - **Prestanda**: ⭐⭐⭐ Okej (kan vara tight)
  - **Körs på**: GPU (delvis) + CPU (delvis)
  - **Hastighet**: Okej, kan vara långsamt ibland

### ❌ **Dålig prestanda** (körs mestadels på CPU):
- **Qwen3-VL:8b** (6.1 GB fil) → ~8-9 GB VRAM
  - **Prestanda**: ⭐⭐ Dålig (för stor)
  - **Körs på**: CPU (mestadels)
  - **Hastighet**: Långsam

- **Gemma3:12b** (8.1 GB fil) → ~10-12 GB VRAM
  - **Prestanda**: ⭐ Dålig (för stor)
  - **Körs på**: CPU (mestadels)
  - **Hastighet**: Mycket långsam

## Rekommendation för RTX 2060 (6 GB VRAM):

### 🥇 **BÄST VAL: Gemma3:4b**
- **Varför**: Perfekt storlek för din GPU
- **Prestanda**: Mycket bra (körs helt på GPU)
- **Hastighet**: Snabb
- **VRAM**: ~4-5 GB (passar perfekt)

### 🥈 **ALTERNATIV: DeepSeek R1:8b**
- **Varför**: Nyare version, kan fungera
- **Prestanda**: Okej (kan vara tight)
- **Hastighet**: Okej, kan vara långsamt
- **VRAM**: ~6-7 GB (tight, kan behöva CPU-hjälp)

### 🥉 **SNARAST: DeepSeek R1:1.5b**
- **Varför**: Mycket liten, mycket snabb
- **Prestanda**: Mycket bra
- **Hastighet**: Mycket snabb
- **VRAM**: ~2 GB (mycket plats över)

## Viktigt:

**Om modellen är för stor för VRAM:**
- Den körs på CPU istället
- CPU är 10-50x långsammare än GPU
- Du får dålig prestanda trots att "det får plats"

**För bästa prestanda:**
- Modellen ska vara < 5 GB fil
- Då får den plats helt i VRAM
- Snabb prestanda på GPU

## Testa prestanda:

```bash
# Testa Gemma3:4b
ollama pull gemma3:4b
time ollama run gemma3:4b "Hej, test"
nvidia-smi  # Kolla GPU-användning

# Om GPU-användning är hög = bra (körs på GPU)
# Om GPU-användning är låg = dåligt (körs på CPU)
```

## Slutsats:

**För din RTX 2060 (6 GB VRAM):**
- **Gemma3:4b** = BÄST prestanda ⭐⭐⭐⭐⭐
- **DeepSeek R1:8b** = Okej prestanda ⭐⭐⭐
- **Qwen3-VL:8b** = Dålig prestanda ⭐⭐ (för stor)

**Rekommendation: Gemma3:4b för bästa prestanda!**
