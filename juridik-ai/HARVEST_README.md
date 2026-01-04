# OPERATION: TOTAL HARVEST

Massiv parallell crawl-operation för att nå **100,000 dokument** i ChromaDB.

## 🎯 Mål

- **CURRENT:** 20,068 dokument (enligt användaren)
- **TARGET:** 100,000 dokument
- **REMAINING:** ~80,000 dokument
- **EST. TIME:** 4-5 timmar med bevisad throughput
- **DISK:** 717 GB tillgängligt (INGEN BEGRÄNSNING)

## 🚀 Snabbstart

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/juridik-ai
python3 total_harvest.py
```

## 📋 Prioritetsordning

Scriptet kör crawlers i denna ordning:

1. **SOU** (kritiskt för juridisk research) → ~3,000 tillgängliga
2. **Interpellationer** (politisk kontext) → ~15,000 tillgängliga
3. **Motioner** (2000-2014, äldre) → ~150,000 tillgängliga
4. **JO-beslut** (myndighetskritik) → ~5,000 tillgängliga
5. **Skriftliga frågor** (volym-fyllnad) → ~80,000 tillgängliga

## ⚙️ Konfiguration

Scriptet använder:
- **Rate limit:** 0.3s mellan requests (aggressiv för harvest)
- **Chunk size:** 1000 tokens per chunk
- **Chunk overlap:** 100 tecken
- **Report interval:** Var 5,000:e dokument

## 📊 Rapportering

Scriptet rapporterar automatiskt:
- Var 5,000:e dokument
- Total chunks i ChromaDB
- Throughput (chunks/sekund)
- ETA till 100k

## 🛑 Stoppa och Återuppta

Scriptet stöder checkpoint/resume:
- Tryck `Ctrl+C` för att stoppa
- Kör samma kommando igen för att återuppta
- Checkpoints sparas i `data/riksdagen/.checkpoint_*.json`

## 📁 Data-struktur

```
data/
├── riksdagen/
│   ├── sou/          # SOU-dokument
│   ├── ip/           # Interpellationer
│   ├── mot/          # Motioner
│   ├── fsk/          # Skriftliga frågor
│   └── .checkpoint_* # Resume-checkpoints
└── jo/               # JO-beslut
```

## 🔍 Verifiera Status

```bash
# Kolla antal dokument i ChromaDB
python3 -c "from cli.brain import get_brain; brain = get_brain(); print(f'Documents: {brain.collection.count()}')"

# Kolla loggfil
tail -f total_harvest.log
```

## ⚠️ Viktigt

- **INGA rate limits** mellan olika myndigheter
- **INGEN batch-storlek-gräns**
- **INGEN nattschema-väntan**
- Circuit breaker ENDAST vid faktiska fel

## 🎉 Efter 100k

När 100k är nått, inventera vad som finns kvar för 500k milestone.
