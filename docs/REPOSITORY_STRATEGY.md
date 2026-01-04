# Repository Strategy - Constitutional AI

## Nuvarande Situation

### Befintliga Repositories

1. **`rag-project`** (GitHub: `itsimonfredlingjack/rag-project`)
   - Generellt RAG-projekt
   - Innehåller: `app/`, `cli/`, `data/`, `docs/`, `systemd/`, `tests/`
   - Verkar vara mer generell backend-struktur

2. **`09_CONSTITUTIONAL-AI`** (Lokalt)
   - Specifikt för Constitutional AI
   - Innehåller: `backend/`, `apps/`, `scrapers/`, `indexers/`, `docs/`
   - Har ny backend-struktur efter migration

## Rekommendation: Ett Repository

### Varför ett repo är bättre:

1. **Monorepo-fördelar**
   - All kod på ett ställe
   - Enklare dependency management
   - Enklare att hålla dokumentation synkad
   - Enklare för AI-modeller att förstå helheten

2. **Constitutional AI är ett komplett projekt**
   - Backend (FastAPI)
   - Frontend (React/Next.js)
   - Scrapers
   - Indexers
   - Dokumentation
   - Allt hänger ihop

3. **AI-förståelse**
   - AI-modeller förstår bättre när allt är i ett repo
   - Enklare att ge kontext
   - Enklare att navigera

### Strategi: Uppdatera `rag-project` eller skapa nytt?

**Alternativ 1: Uppdatera `rag-project` (REKOMMENDERAT)**
- ✅ Redan existerande repo
- ✅ Har redan backend-struktur
- ✅ Kan migrera till Constitutional AI-struktur
- ⚠️ Måste rensa/uppdatera gamla filer

**Alternativ 2: Skapa nytt repo `constitutional-ai`**
- ✅ Ren start
- ✅ Tydligare namn
- ❌ Måste migrera från `rag-project`
- ❌ Två repos att underhålla

## Rekommenderad Lösning: Uppdatera `rag-project`

### Plan:

1. **Pusha `09_CONSTITUTIONAL-AI` till `rag-project`**
   - Behåll repo-namnet (kan byta senare)
   - Pusha all ny backend-logik
   - Pusha all dokumentation

2. **Struktur i repo:**
   ```
   rag-project/
   ├── backend/              # NY: Constitutional AI Backend
   │   ├── app/
   │   │   ├── api/
   │   │   ├── services/
   │   │   └── main.py
   │   └── requirements.txt
   ├── apps/                 # NY: Frontend apps
   │   ├── constitutional-gpt/
   │   └── constitutional-dashboard/
   ├── scrapers/            # NY: Web scrapers
   ├── indexers/            # NY: Indexing scripts
   ├── docs/                # UPPDATERAD: Dokumentation
   ├── README.md            # UPPDATERAD: Constitutional AI
   ├── AI-INDEX.md          # NY: AI-specifik index
   └── [gamla filer kan behållas eller tas bort]
   ```

3. **Uppdatera README.md**
   - Byt fokus från generell RAG till Constitutional AI
   - Uppdatera beskrivning
   - Lägg till länkar till dokumentation

## Implementation Steps

### Steg 1: Koppla lokalt repo till GitHub

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI

# Kolla om remote redan finns
git remote -v

# Om inte, lägg till remote
git remote add origin https://github.com/itsimonfredlingjack/rag-project.git

# Eller uppdatera om den redan finns
git remote set-url origin https://github.com/itsimonfredlingjack/rag-project.git
```

### Steg 2: Verifiera .gitignore

```bash
# Kontrollera att stora mappar är exkluderade
cat .gitignore | grep -E "chromadb_data|pdf_cache|backups"
```

### Steg 3: Stage alla ändringar

```bash
# Stage allt (inklusive nya backend/)
git add .

# Kontrollera vad som ska committas
git status
```

### Steg 4: Commit med beskrivande meddelande

```bash
git commit -m "feat: Migrate Constitutional AI backend and add comprehensive documentation

- Migrated backend from 02_SIMONS-AI-BACKEND to 09_CONSTITUTIONAL-AI/backend
- Added complete backend structure (FastAPI, services, API routes)
- Added frontend apps (constitutional-gpt, constitutional-dashboard)
- Added comprehensive documentation (AI-INDEX.md, README.md, docs/)
- Updated all service references to constitutional-ai-backend
- Added GitHub publication guide for AI models"
```

### Steg 5: Push till GitHub

```bash
# Första gången (om repo är tomt)
git push -u origin main

# Eller om det finns content redan
git pull origin main --allow-unrelated-histories
git push origin main

# Om det finns konflikter, merge först
```

## Alternativ: Skapa nytt repo

Om du vill ha ett nytt repo istället:

```bash
# Skapa nytt repo på GitHub: constitutional-ai

cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI

git remote remove origin  # Om den finns
git remote add origin https://github.com/itsimonfredlingjack/constitutional-ai.git
git push -u origin main
```

## Rekommendation: Ett repo är bäst

**Varför:**
1. ✅ Allt hänger ihop - backend, frontend, scrapers
2. ✅ Enklare för AI-modeller att förstå
3. ✅ Enklare dependency management
4. ✅ Enklare dokumentation
5. ✅ Enklare att underhålla

**När flera repos är bättre:**
- Om du har flera helt separata produkter
- Om du har olika teams som arbetar med olika delar
- Om du har olika release cycles

**För Constitutional AI:**
- Allt är en produkt
- Backend och frontend hänger ihop
- Scrapers är del av samma system
- Ett repo är optimalt

## Nästa steg

1. ✅ Koppla lokalt repo till GitHub
2. ✅ Verifiera .gitignore
3. ✅ Stage alla ändringar
4. ✅ Commit med beskrivande meddelande
5. ✅ Push till GitHub

Se `docs/GITHUB_PUBLICATION_GUIDE.md` för detaljerad guide.
