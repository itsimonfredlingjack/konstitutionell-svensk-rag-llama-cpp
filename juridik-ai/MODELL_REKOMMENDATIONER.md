# Modell-rekommendationer (Uppdaterad)

## Nuvarande: DeepSeek R1:7b
- Fungerar men har problem med svenska
- Vi har optimerat system prompten och parametrar för bättre resultat

## Bättre alternativ (INTE kinesiska):

### 1. **Phi 4 Mini** (NYAST - från Microsoft, 3.8B, 2.5GB) ⭐ NY REKOMMENDATION
```bash
ollama pull phi4-mini
```
- **Fördelar**: Nyaste modellen, mycket liten (2.5 GB), snabb, från Microsoft
- **Storlek**: 2.5 GB
- **Betyg**: ⭐⭐⭐⭐⭐ (NY - testa denna först!)
- **Rekommenderad - nyaste och minsta!**

### 2. **Llama 3.1:8b** (BÄST för svenska, från Meta/Facebook)
```bash
ollama pull llama3.1:8b
```
- **Fördelar**: Utmärkt svenska, västerländsk modell, stabil
- **Storlek**: 4.7 GB
- **Betyg**: ⭐⭐⭐⭐⭐
- **Rekommenderad för svenska!**

### 2. **Mistral:7b** (Från Frankrike)
```bash
ollama pull mistral:7b
```
- **Fördelar**: Bra svenska, snabb, liten fil
- **Storlek**: 4.1 GB
- **Betyg**: ⭐⭐⭐⭐

### 3. **Phi-3:mini** (Från Microsoft)
```bash
ollama pull phi3:mini
```
- **Fördelar**: Mycket liten (2.3 GB), snabb, bra svenska
- **Storlek**: 2.3 GB
- **Betyg**: ⭐⭐⭐

## UNDVIK (kinesiska modeller):
- Qwen (kinesisk)
- Yi (kinesisk)
- ChatGLM (kinesisk)

## Rekommendation:

**FÖRST - Testa Phi 4 Mini** (nyaste, minsta, från Microsoft):
```bash
ollama pull phi4-mini
```
- Nyaste modellen
- Mycket liten (2.5 GB vs 4.7 GB)
- Snabb
- Från Microsoft (västerländsk)

**Alternativ för bästa svenska**: `llama3.1:8b` (från Meta)
- Utmärkt svenska
- Stabil och pålitlig
- Samma storlek som nuvarande (4.7 GB)

## Så här byter du (om du vill):

1. **Ladda ner:**
   ```bash
   ollama pull llama3.1:8b
   ```

2. **Uppdatera config:**
   Redigera `~/.config/deepseek-cli/config.toml`:
   ```toml
   [model]
   name = "llama3.1:8b"
   ```

3. **Starta om CLI:et**

## Men först - testa nuvarande setup!

Jag har optimerat:
- ✅ System prompten (kortfattat, tydligt)
- ✅ Temperature (0.3 istället för 0.7 - mer fokuserat)
- ✅ Top_P (0.8 istället för 0.9 - mindre slumpmässigt)

Testa först med DeepSeek - det borde vara bättre nu!
