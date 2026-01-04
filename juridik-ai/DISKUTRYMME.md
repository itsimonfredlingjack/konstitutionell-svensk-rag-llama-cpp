# Diskutrymme och modell-storlekar

## Nuvarande modell:
- **DeepSeek R1:7b** - 4.7 GB

## Modeller du överväger:

### Qwen3-VL:8b - 6.1 GB
- **Extra utrymme behövs**: 6.1 - 4.7 = **+1.4 GB**
- **Total med båda**: ~11 GB (om du behåller gamla)

### Gemma3:12b - 8.1 GB  
- **Extra utrymme behövs**: 8.1 - 4.7 = **+3.4 GB**
- **Total med båda**: ~13 GB

### DeepSeek R1:8b - 5.2 GB
- **Extra utrymme behövs**: 5.2 - 4.7 = **+0.5 GB**
- **Total med båda**: ~10 GB

### Gemma3:4b - 3.3 GB
- **Sparar utrymme**: 4.7 - 3.3 = **-1.4 GB**
- **Mindre än nuvarande!**

## Rekommendationer baserat på utrymme:

### Om du har < 5 GB ledigt:
- **Gemma3:4b** (3.3 GB) - mindre än nuvarande
- **DeepSeek R1:1.5b** (1.1 GB) - mycket liten

### Om du har 5-10 GB ledigt:
- **DeepSeek R1:8b** (5.2 GB) - bara +0.5 GB
- **Qwen3-VL:8b** (6.1 GB) - +1.4 GB

### Om du har > 10 GB ledigt:
- **Qwen3-VL:8b** (6.1 GB) - bäst balans
- **Gemma3:12b** (8.1 GB) - bäst tänkande

## Tips:

1. **Du kan ta bort gamla modellen** om du byter:
   ```bash
   ollama rm deepseek-r1:7b
   ```
   Då behöver du bara extra utrymme för skillnaden!

2. **Qwen3-VL:8b behöver bara +1.4 GB** om du tar bort gamla
3. **Gemma3:4b sparar faktiskt utrymme** (-1.4 GB)

## Praktiskt:

**Säkraste val**: Gemma3:4b (3.3 GB)
- Sparar utrymme
- Bra svenska
- Vision support

**Bästa val om du har plats**: Qwen3-VL:8b (6.1 GB)
- Bara +1.4 GB om du tar bort gamla
- Bäst balans
