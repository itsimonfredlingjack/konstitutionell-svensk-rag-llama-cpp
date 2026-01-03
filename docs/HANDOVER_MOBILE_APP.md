# Överlämning: Mobilapp-integration

## Backend API

**Server:** `192.168.86.32:8000`

### WebSocket Chat
```
ws://192.168.86.32:8000/api/chat
```

**Skicka meddelande:**
```json
{
  "type": "chat",
  "profile": "gpt-oss",
  "messages": [{"role": "user", "content": "Hej!"}],
  "request_id": "unique-id-123"
}
```

**Ta emot (streaming):**
```json
{"type": "start", "agent_id": "gpt-oss"}
{"type": "token", "content": "Hej"}
{"type": "token", "content": "!"}
{"type": "done", "stats": {...}}
```

### Tillgängliga modeller

| Profile ID | Modell | Beskrivning |
|------------|--------|-------------|
| `gpt-oss` | GPT-OSS 20B | Arkitekt - resonemang, planering |
| `devstral` | Devstral 24B | Kodare - implementation |

### REST Endpoints
```
GET  /api/health              # Systemstatus
POST /api/profiles/{id}/warmup # Värm upp modell
```

## Viktigt för mobilappen

1. **WebSocket-format:** Samma som ovan
2. **Streaming:** Tokens kommer en i taget, buffra och visa
3. **Profile-switch:** Skicka annat `profile`-värde för att byta modell
4. **Request ID:** Generera unikt ID per meddelande (UUID)

## Exempel: Minimal klient

```javascript
const ws = new WebSocket('ws://192.168.86.32:8000/api/chat');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'token') {
    // Visa token i chatten
    appendToChat(data.content);
  }
};

// Skicka meddelande
ws.send(JSON.stringify({
  type: 'chat',
  profile: 'gpt-oss',
  messages: [{role: 'user', content: 'Hej!'}],
  request_id: crypto.randomUUID()
}));
```
