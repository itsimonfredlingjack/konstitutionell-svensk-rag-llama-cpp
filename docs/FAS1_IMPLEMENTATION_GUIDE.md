# Fas 1: Omedelbar Hårdvaruoptimering - Implementeringsguide

**Status**: ✅ Modellerna finns redan! llama-server finns men körs inte.

## ✅ Modeller Verifierade

- **Mistral-Nemo-Instruct-2407-Q5_K_M.gguf**: 8.2GB
  - Plats: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/models/`
  
- **Qwen2.5-0.5B-Instruct-Q8_0.gguf**: 645MB
  - Plats: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/models/`

## Steg 1: Skapa systemd-service

Kopiera service-filen till systemd:

```bash
sudo cp /tmp/llama-server.service /etc/systemd/system/llama-server.service
```

Eller skapa den manuellt:

```bash
sudo nano /etc/systemd/system/llama-server.service
```

Klistra in följande:

```ini
[Unit]
Description=llama-server with KV-cache quantization and speculative decoding
After=network.target

[Service]
Type=simple
User=ai-server
WorkingDirectory=/home/ai-server
ExecStart=/home/ai-server/llama.cpp/build/bin/llama-server \
  --model /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf \
  --draft-model /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/models/Qwen2.5-0.5B-Instruct-Q8_0.gguf \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  -c 8192 \
  -ngl 99 \
  --port 8080 \
  --host 0.0.0.0

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment="CUDA_VISIBLE_DEVICES=0"

[Install]
WantedBy=multi-user.target
```

## Steg 2: Aktivera och starta

```bash
sudo systemctl daemon-reload
sudo systemctl enable llama-server
sudo systemctl start llama-server
```

## Steg 3: Verifiering

### 3.1 Kontrollera att servicen körs
```bash
sudo systemctl status llama-server
```

### 3.2 Kontrollera loggar för KV cache
```bash
sudo journalctl -u llama-server -f | grep -i "cache\|q8\|draft"
```

Du bör se något liknande:
```
KV cache type: Q8_0
Draft model loaded: Qwen2.5-0.5B-Instruct-Q8_0.gguf
```

### 3.3 Testa API
```bash
curl http://localhost:8080/v1/models | python3 -m json.tool
```

### 3.4 Kontrollera minnesanvändning
```bash
nvidia-smi
# eller
watch -n 1 nvidia-smi
```

Du bör se att VRAM-användningen är lägre än tidigare tack vare KV-cache kvantisering.

## Förväntade Resultat

- ✅ KV cache kvantiserad till Q8_0 (halverar minnesanvändning)
- ✅ Spekulativ avkodning aktiverad (1.5x-2x hastighetsökning)
- ✅ Kontextfönster 8k tokens (tack vare cache-kvantisering)
- ✅ Alla lager på GPU (-ngl 99)
- ✅ Stabil drift utan OOM-krascher

## Felsökning

**Problem: Modellen hittas inte**
- Kontrollera sökvägen i systemd-service
- Verifiera att modellerna finns: `ls -lh /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/models/*.gguf`

**Problem: OOM (Out Of Memory)**
- Minska kontextfönstret: `-c 4096` istället för `-c 8192`
- Eller minska GPU layers: `-ngl 80` istället för `-ngl 99`

**Problem: Port 8080 redan används**
- Ändra port: `--port 8081`
- Uppdatera config i backend: `CONST_LLM_BASE_URL=http://localhost:8081/v1`

**Problem: Service startar inte**
- Kontrollera loggar: `sudo journalctl -u llama-server -n 50`
- Verifiera att llama-server är körbar: `ls -l /home/ai-server/llama.cpp/build/bin/llama-server`
- Kontrollera behörigheter: `sudo chmod +x /home/ai-server/llama.cpp/build/bin/llama-server`
