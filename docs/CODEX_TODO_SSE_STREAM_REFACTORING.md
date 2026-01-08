# CODEX TODO: SSE Stream Refactoring & Frontend Fixes

## Bakgrund
- Backend kör FastAPI på port 8900.
- LLM-backend är llama-server (llama.cpp) på port 8080.
- Modell: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf.
- Ingen Ollama/ministral-3:14b i denna stack.

## Mål
1) Bryt ut SSE-klient till separat service i frontend med callbacks.
2) Inför automatisk retry för SSE (om möjligt med Last-Event-ID, annars manuell).
3) Hantera keep-alive ping-meddelanden utan JSON-parse crash.
4) Lägg till Canvas dpr-tak för bättre GPU-prestanda.
5) Ersätt hårdkodad backend-URL med env-variabel.
6) Lägg till backend keep-alive ping för SSE var 15:e sekund.

---

## Backend

### 1) Ny service för SSE keep-alive
**Ny fil**: `backend/app/services/sse_stream_service.py`

Skapa en wrapper som tar en AsyncGenerator[str] och injicerar keep-alive-kommentarer om ingen data kommer på 15 sekunder.

Exempelmönster:
- Vänta på nästa event med `asyncio.wait_for`.
- Vid timeout: `yield ":\n\n"` (SSE comment ping).
- Vid StopAsyncIteration: avsluta.
- Vid exception: yield error-event (data: {type: "error", message: ...}).

### 2) Använd keep-alive i endpoint
**Fil**: `backend/app/api/constitutional_routes.py`

Uppdatera `agent_query_stream` så att den använder SSE-stream-wrapper.
- Importera service.
- Wrap `orchestrator.stream_query(...)` i keep-alive wrapper.
- Behåll headers: `Cache-Control`, `Connection`, `X-Accel-Buffering`.

### 3) (Valfritt men önskat) Last-Event-ID stöd
Om möjligt, lägg event-ID i SSE för resume:
- Skicka `id:` per event.
- Läs `Last-Event-ID` header och försök återuppta.

Om detta är för tungt just nu, kör manuell retry i frontend utan resume.

---

## Frontend

### 4) StreamClient service
**Ny fil**: `apps/constitutional-retardedantigravity/src/services/streamClient.ts`

Skapa en service som tar callbacks:
- `onToken(token)`
- `onMetadata(meta)`
- `onDone(data)`
- `onError(message)`
- (valfritt) `onDecontextualized`, `onCorrections`

Struktur:
- `StreamClient.query(question, { onToken, onMetadata, onDone, onError }, options)`
- Hantera fetch + stream + SSE-parsing
- Ignorera keep-alive rader som börjar med ":"
- Retry vid nätverksfel (max 3, exponential backoff)

### 5) Refactor store till callbacks
**Fil**: `apps/constitutional-retardedantigravity/src/stores/useAppStore.ts`

- Ta bort all SSE-hantering från store.
- Anropa `StreamClient.query(...)` med callbacks.
- Uppdatera state i callbacks:
  - `onToken`: append till `answer`
  - `onMetadata`: sätt `sources`, `evidenceLevel`
  - `onDone`: markera `isSearching=false`, `searchStage=complete`
  - `onError`: sätt `error` och `searchStage=error`

### 6) Fix för ping-meddelanden
**Fil**: `apps/constitutional-retardedantigravity/src/stores/useAppStore.ts`

I SSE-parser-loopen (om den finns kvar), lägg till:
```ts
if (!eventBlock.trim()) continue;
if (eventBlock.startsWith(':')) continue; // keep-alive ping
```

### 7) Env för backend URL
**Ny fil**: `apps/constitutional-retardedantigravity/.env`
```
VITE_BACKEND_URL=http://192.168.86.32:8900
```

### 8) Byt hårdkodad URL
**Fil**: `apps/constitutional-retardedantigravity/src/stores/useAppStore.ts`

Ersätt:
```ts
const BACKEND_URL = 'http://192.168.86.32:8900';
```
med:
```ts
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8900';
```

### 9) Canvas DPR-tak
**Fil**: `apps/constitutional-retardedantigravity/src/App.tsx`

Lägg till på `<Canvas>`:
```tsx
<Canvas
  dpr={[1, 2]}
  camera={{ position: [0, 2, 8], fov: 50 }}
  gl={{ antialias: true, powerPreference: "high-performance" }}
>
```

---

## Verifiering

### Backend
- Testa SSE keep-alive med curl:
```
curl -N http://localhost:8900/api/constitutional/agent/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"test","mode":"auto"}'
```
- Bekräfta att `:\n\n` skickas vid inaktivitet.

### Frontend
- Starta appen och kör en query.
- Verifiera:
  - Inga JSON-parse errors från ping
  - Retry fungerar vid kort nätverksavbrott
  - Canvas prestanda bättre på 3x skärm

---

## Notering
Följ backendens verkliga LLM-konfiguration:
- llama.cpp / llama-server (OpenAI-kompatibel)
- Port 8080
- Modell: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf
