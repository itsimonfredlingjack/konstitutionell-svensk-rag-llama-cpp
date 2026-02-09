# MCP Server - Quick Reference

## 🎯 Status: LIVE & RUNNING ✅

**Service:** `mcp-server.service` (enabled, auto-start on boot)
**Port:** 8002
**Endpoint:** http://localhost:8002/mcp
**External URL:** https://mcp.fredlingautomation.dev/mcp (once DNS is configured)

## 📊 Service Commands

```bash
# Check status
sudo systemctl status mcp-server

# View logs (live)
journalctl -u mcp-server -f

# View recent logs
journalctl -u mcp-server -n 50

# Restart service
sudo systemctl restart mcp-server

# Stop service
sudo systemctl stop mcp-server

# Disable auto-start
sudo systemctl disable mcp-server
```

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `/etc/systemd/system/mcp-server.service` | Systemd service definition |
| `.env.mcp` | Environment variables (API keys, settings) |
| `mcp_server/main.py` | Server code with 4 tools |
| `~/.cloudflared/config.yml` | Cloudflare tunnel config (UPDATED ✅) |

## 🛠️ Available Tools

1. **read_file** - Read file contents with optional line range
2. **write_file** - Write/create files (with automatic backup)
3. **list_files** - List directory contents (supports glob patterns)
4. **search_files** - Search code with ripgrep

## 🚀 Next Steps

### 1. Restart Cloudflared (Manual)
```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
```

### 2. Add DNS Record in Cloudflare Dashboard
- Go to: https://dash.cloudflare.com
- Select: `fredlingautomation.dev`
- DNS → Add record:
  - **Type:** CNAME
  - **Name:** mcp
  - **Target:** `0aaa6c91-1c22-4fe6-bd31-e48a76543cdf.cfargotunnel.com`
  - **Proxy:** Enabled (orange cloud) ☁️

### 3. Test External Access
Wait 1-2 minutes for DNS to propagate, then:
```bash
curl -X POST https://mcp.fredlingautomation.dev/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Should return JSON with `serverInfo: {"name":"simons-ai-mcp",...}`

### 4. Connect from Claude.ai
1. Go to: https://claude.ai/
2. Settings → **Integrations** (or **Connectors**)
3. Click **Add custom connector**
4. Fill in:
   - **Name:** Simon's AI MCP Server
   - **Remote MCP server URL:** `https://mcp.fredlingautomation.dev/mcp`
   - **OAuth Client ID:** *(leave empty)*
   - **OAuth Client Secret:** *(leave empty)*
5. Click **Save** or **Connect**

### 5. Test Tools from Claude.ai
Once connected, try asking Claude:
- "List files in /home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/"
- "Read the file app/main.py"
- "Search for 'FastAPI' in Python files"

## ⚠️ Important Notes

- **No Authentication Yet:** API key auth is implemented but not integrated with FastMCP
- **Only File Operations:** Git and system tools are not implemented yet
- **Auto-start Enabled:** MCP server will start automatically on boot
- **Port 8002:** Make sure this port stays free (not used by other services)

## 🔍 Troubleshooting

### Service won't start?
```bash
# Check for errors
journalctl -u mcp-server -n 100

# Check if port is in use
lsof -i :8002

# Test manually
venv/bin/python -m mcp_server.main
```

### Can't access externally?
1. Check cloudflared: `systemctl status cloudflared`
2. Check DNS record exists in Cloudflare
3. Wait 2-5 minutes for DNS propagation
4. Test with curl (see above)

### Tools not working?
1. Check MCP server logs: `journalctl -u mcp-server -f`
2. Verify file paths are within `/home/ai-server/01_PROJECTS/`
3. Check file permissions

## 📚 Documentation

- Full setup guide: `MCP_SERVER_SETUP.md`
- Implementation plan: `~/.claude/plans/cozy-juggling-tome.md`
- FastMCP docs: https://gofastmcp.com
- MCP spec: https://spec.modelcontextprotocol.io/

## 🔑 API Key (Not Active)

Stored in `.env.mcp`:
```
MCP_API_KEY_PROD=mcp_sk_yI4PQ8U8S_eVLfpKhVlB8sMJQCCq8Cw1AhSblNwgYHk
```

*Note: Currently not enforced - server is open access behind Cloudflare*

---

**Last Updated:** 2025-12-03 19:59 UTC
**Version:** MVP 1.0
**Status:** ✅ Production Ready (with limitations)
