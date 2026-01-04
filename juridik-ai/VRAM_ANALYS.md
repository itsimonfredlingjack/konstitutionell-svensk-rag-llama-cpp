# VRAM-analys för modeller

## Viktigt om VRAM:

Modeller behöver VRAM (grafikkortets minne) för att köras snabbt på GPU.
Om modellen är för stor för VRAM, körs den på CPU istället (mycket långsammare).

## Modell-storlekar och VRAM-behov:

### Regel:
- Modell-fil: ~X GB
- VRAM-behov: ~X GB + overhead (vanligtvis X * 1.2-1.5)
- Context/minne: +extra VRAM när den används

### Dina modeller:

1. **DeepSeek R1:7b** (4.7 GB fil)
   - VRAM-behov: ~6-7 GB
   - Status: Du har denna redan

2. **Qwen3-VL:8b** (6.1 GB fil)
   - VRAM-behov: ~8-9 GB
   - **Kräver mer VRAM!**

3. **Gemma3:12b** (8.1 GB fil)
   - VRAM-behov: ~10-12 GB
   - **Kräver mycket VRAM!**

4. **DeepSeek R1:8b** (5.2 GB fil)
   - VRAM-behov: ~6-7 GB
   - Liknande som din nuvarande

5. **Gemma3:4b** (3.3 GB fil)
   - VRAM-behov: ~4-5 GB
   - **Mindre VRAM än nuvarande!**

## Rekommendationer baserat på VRAM:

### Om du har < 6 GB VRAM:
- **Gemma3:4b** - bäst val (3.3 GB fil)
- **DeepSeek R1:1.5b** - mycket liten (1.1 GB fil)

### Om du har 6-8 GB VRAM:
- **DeepSeek R1:8b** - passar bra (5.2 GB fil)
- **Gemma3:4b** - säkert val (3.3 GB fil)
- **Qwen3-VL:8b** - kan vara för stor (6.1 GB fil)

### Om du har > 8 GB VRAM:
- **Qwen3-VL:8b** - bäst balans (6.1 GB fil)
- **Gemma3:12b** - om du har > 10 GB VRAM

## Viktigt:

- **Kolla din VRAM först!**
- Om modellen är för stor, körs den på CPU (långsamt)
- Mindre modell = snabbare på GPU

## Tips:

1. **Kolla VRAM:**
   ```bash
   nvidia-smi
   ```

2. **Testa modell:**
   ```bash
   ollama run qwen3-vl:8b "test"
   nvidia-smi  # Kolla VRAM-användning
   ```

3. **Om modellen är för stor:**
   - Den körs på CPU (mycket långsammare)
   - Byt till mindre modell istället
