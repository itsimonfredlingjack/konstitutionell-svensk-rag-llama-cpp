# Optimering av lokala AI-modeller

## Typer av optimering:

### 1. **Quantization (Kvantisering)** - Minska modellstorlek
- **4-bit quantization**: Minskar storlek med ~75%, lite sämre kvalitet
- **8-bit quantization**: Minskar storlek med ~50%, bättre kvalitet
- **Exempel**: Gemma3:4b (3.3GB) → Gemma3:4b-Q4 (0.8GB)

**Fördelar:**
- Mindre VRAM-användning
- Snabbare laddning
- Mer plats för större context

**Nackdelar:**
- Lite sämre kvalitet
- Kan vara långsammare på vissa GPU:er

### 2. **Context Length** - Justera minne
- **Nuvarande**: 4096 tokens (~3000 ord)
- **Öka**: 8192, 16384 tokens (mer minne, mer VRAM)
- **Minska**: 2048 tokens (mindre VRAM, snabbare)

**Fördelar med större context:**
- Kan hålla mer i minnet
- Bättre för långa konversationer

**Nackdelar:**
- Mer VRAM-användning
- Långsammare

### 3. **Temperature & Top_P** (Vi har redan optimerat!)
- **Temperature**: 0.3 (lägre = mer fokuserat, högre = mer kreativt)
- **Top_P**: 0.8 (lägre = mer förutsägbart, högre = mer varierat)

### 4. **Ollama-specifika inställningar**
- **num_ctx**: Context length (4096, 8192, etc.)
- **num_gpu**: Antal GPU-lager att använda
- **num_thread**: CPU-trådar (om delvis CPU)

### 5. **GPU-optimering**
- **CUDA settings**: Justera GPU-minneshantering
- **Batch size**: För batch-inferens (inte relevant för chat)

## Praktiska optimeringar för din setup:

### A. **Quantized modeller** (om du vill ha mindre/snabbare):

```bash
# Kolla om det finns quantized versioner
ollama pull gemma3:4b-q4_0  # 4-bit (mycket mindre)
ollama pull gemma3:4b-q8_0  # 8-bit (lite mindre)
```

### B. **Justera context length** (i config.toml):

```toml
[model]
context_length = 8192  # Öka för mer minne
# eller
context_length = 2048  # Minska för snabbare
```

### C. **Ollama environment variables**:

```bash
# Öka GPU-användning
export OLLAMA_NUM_GPU=1
export OLLAMA_NUM_CTX=4096

# Justera CPU-trådar (om delvis CPU)
export OLLAMA_NUM_THREAD=4
```

### D. **System prompt optimering** (Vi har redan gjort!)
- Kortfattat = snabbare svar
- Tydliga instruktioner = bättre resultat

## Rekommendationer för din RTX 2060 (6GB VRAM):

### ✅ **Redan optimerat:**
- Temperature: 0.3 (fokuserat)
- Top_P: 0.8 (balanserat)
- System prompt: Kortfattat, tydligt

### 💡 **Ytterligare optimeringar du kan testa:**

1. **Testa quantized version** (om den finns):
   ```bash
   ollama pull gemma3:4b-q4_0
   # Uppdatera config.toml: name = "gemma3:4b-q4_0"
   ```
   - Mycket mindre VRAM
   - Snabbare
   - Lite sämre kvalitet

2. **Justera context** (om du behöver mer minne):
   ```toml
   context_length = 8192  # Mer minne
   ```

3. **GPU-optimering** (i ~/.bashrc eller ~/.zshrc):
   ```bash
   export OLLAMA_NUM_GPU=1
   export OLLAMA_GPU_LAYERS=35  # Antal lager på GPU
   ```

## Testa prestanda:

```bash
# Testa nuvarande
time ollama run gemma3:4b "Test"

# Testa quantized (om tillgänglig)
time ollama run gemma3:4b-q4_0 "Test"

# Jämför hastighet och kvalitet
```

## Viktigt:

- **Quantization**: Bra för att spara VRAM, men kan påverka kvalitet
- **Context**: Större = mer minne men mer VRAM
- **Temperature**: Vi har redan optimerat (0.3)
- **System prompt**: Vi har redan optimerat

## För din setup:

**Nuvarande optimering är bra!** Gemma3:4b passar perfekt för din GPU.

**Om du vill testa mer:**
- Kolla om det finns `gemma3:4b-q4_0` eller `gemma3:4b-q8_0`
- Testa och jämför hastighet/kvalitet
