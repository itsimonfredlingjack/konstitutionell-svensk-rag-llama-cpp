# Agent Guardrails

## Route Discovery (OBLIGATORISKT)

Innan du påstår att en endpoint saknas:

1. **Grep routes:**
   ```bash
   grep -r "router\|@app\|@router" app/api/
   ```

2. **Check OpenAPI:**
   ```bash
   curl http://localhost:8900/docs
   ```

3. **Read source:**
   ```bash
   cat 09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py
   ```

4. **Verify endpoint exists:**
   ```bash
   curl -X POST http://localhost:8900/api/constitutional/search \
     -H "Content-Type: application/json" \
     -d '{"query":"test","limit":10}'
   ```

## Service Management

### Statusöversikt

| Tjänst                    | Status     | Port | Autostart   |
|---------------------------|------------|------|-------------|
| Constitutional AI Backend | 🟢 Active  | 8900 | ✅ Enabled  |
| Simons AI Backend         | 🔴 Removed | -    | ❌ Disabled |

### Before Starting Anything

```bash
# Check what's running
lsof -i :8900    # Backend
lsof -i :3001    # Frontend
lsof -i :8080    # llama-server

# Check systemd services
systemctl --user status constitutional-ai-backend
systemctl --user status constitutional-gpt

# Check llama-server health
curl localhost:8080/health

# (Optional) Check Ollama if used as fallback:
# curl localhost:8080/health    # llama-server status
# Check loaded model info
```

### System Commands

```bash
# Status
systemctl --user status constitutional-ai-backend

# Restart
systemctl --user restart constitutional-ai-backend

# Live logs
journalctl --user -u constitutional-ai-backend -f

# Stop vid behov
systemctl --user stop constitutional-ai-backend
```

### API Base URL

```
http://localhost:8900/api/constitutional
```

### Rules

- **NEVER** `systemctl restart` without explicit user order
- **NEVER** `npm run dev` on occupied ports
- **ALWAYS** check `lsof -i :PORT` before starting anything
- **REPORT** port conflicts, don't try to fix automatically

### If Service is Down

1. Report: "Service X is down on port Y"
2. Ask: "Ska jag starta om den?"
3. Wait for confirmation
4. Then: `sudo systemctl restart X`

## Browser Automation

### Rules

- **NEVER** use Playwright/Selenium without explicit permission
- **PREFER** API tests over UI tests
- **IF** UI test needed: ask first

### Why

- Browser automation can interfere with running services
- Requires additional permissions
- Slower and more fragile than API tests

## Error Handling

### 404 Not Found

1. **DON'T** immediately try alternative approaches
2. **DO** route discovery (see above)
3. **REPORT**: "Endpoint X not found according to route discovery"
4. **SUGGEST**: "Ska jag skapa den?"
5. **WAIT** for confirmation

### Timeout

1. Increase timeout
2. Retry max 2 times
3. If still fails: report and wait

### Unknown Error

1. Log full error
2. Report to user
3. Don't guess - wait for instructions

## Testing Strategy

### Backend Testing

```bash
# Health check
curl http://localhost:8900/api/health | jq .

# Search test
curl -X POST http://localhost:8900/api/constitutional/search \
  -H "Content-Type: application/json" \
  -d '{"query":"regeringsformen","limit":5}' | jq .

# GPU stats
curl http://localhost:8900/api/gpu/stats | jq .
```

### Frontend Testing

- Frontend is **client-side** - test manually in browser
- Open: `http://localhost:3001`
- Check console.log in DevTools (F12)
- **NEVER** try to automate without permission

### Evaluation Testing

```bash
# Quick eval (2 min)
constitutional eval --quick

# Full eval (5 min)
constitutional eval --full

# With lightweight metrics (no RAGAS)
constitutional eval --quick --provider lightweight
```

## File Operations

### Safe Operations

- Read any file
- Write to `eval/results/`
- Write to `docs/`
- Write to `scraped_data/`

### Dangerous Operations (Ask First)

- Modify `constitutional_routes.py`
- Modify `agent-loop.ts`
- Modify systemd service files
- Delete ChromaDB data
- Restart services

## Common Mistakes to Avoid

### ❌ DON'T

```bash
# Starting dev server on occupied port
npm run dev  # Port 3001 already in use!

# Restarting service without asking
systemctl --user restart constitutional-gpt  # NEVER without permission!

# Assuming endpoint exists
curl http://localhost:8900/api/chat  # Doesn't exist!

# Using Playwright without permission
playwright codegen http://localhost:3001  # Ask first!
```

### ✅ DO

```bash
# Check first
lsof -i :3001

# Ask before restarting
# "Service X seems down. Ska jag starta om den?"

# Verify endpoint exists
grep -r "/api/chat" app/api/

# Request permission
# "Jag behöver testa UI med Playwright. OK?"
```

## Escalation

If you're stuck:

1. **Report** what you tried
2. **Show** error messages
3. **Suggest** next steps
4. **Wait** for user decision

Don't keep trying random things - ask for help!

## Modelloptimering och Prompt Engineering

### Modellparametrar

**ALDRIG ändra modellparametrar utan dokumentation:**
- Temperature, top_p, repeat_penalty, num_predict ska dokumenteras
- Ändringar ska testas innan deployment
- Se `docs/MODEL_OPTIMIZATION.md` för nuvarande värden

**Nuvarande parametrar (2025-12-15):**
- EVIDENCE: temperature=0.2, top_p=0.9, repeat_penalty=1.1, num_predict=1024
- ASSIST: temperature=0.4, top_p=0.9, repeat_penalty=1.1, num_predict=1024
- CHAT: temperature=0.7, top_p=0.9, repeat_penalty=1.1, num_predict=512

### System Prompts

**ALDRIG ändra system prompts utan att:**
1. Förstå vad prompten gör
2. Testa ändringen med olika frågor
3. Dokumentera ändringen i `docs/MODEL_OPTIMIZATION.md`

**Best Practices:**
- Prompts ska referera till korpusen (1.37M+ dokument: 538K legal/gov + 829K DiVA)
- Prompts ska instruera modellen att använda källor från ChromaDB
- Prompts ska vara tydliga om vad modellen ska göra när källor saknas
- Prompts ska prioritera SFS-källor (lagtext) över prop/sou

**Se `docs/MODEL_OPTIMIZATION.md` för detaljerade prompts.**

### Vad man INTE ska göra (baserat på tidigare misstag)

**ALDRIG:**
- Ändra modellparametrar utan att testa först
- Ta bort instruktioner om källanvändning från prompts
- Ignorera korpusen i system prompts
- Använda generiska prompts utan kontext om korpusen
- Ändra prompts utan att dokumentera ändringarna

**ALLTID:**
- Testa modelländringar med olika frågor
- Dokumentera ändringar i `docs/MODEL_OPTIMIZATION.md`
- Referera till korpusen i prompts
- Instruera modellen att använda källor när de finns
- Var tydlig om vad modellen ska göra när källor saknas
