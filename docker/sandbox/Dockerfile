# AI Code Sandbox - Säker kodexekvering (Grok tip)
# Isolerad miljö utan nätverksåtkomst för säker kodkörning

FROM python:3.11-slim

# Installera vanliga Python-paket för kodexekvering
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    requests \
    pydantic \
    httpx \
    aiohttp \
    beautifulsoup4 \
    lxml

# Skapa användare utan root-privilegier
RUN useradd -m -s /bin/bash sandbox

# Sätt arbetskatalog
WORKDIR /sandbox

# Byt till sandbox-användare
USER sandbox

# Default: kör Python
CMD ["python"]
