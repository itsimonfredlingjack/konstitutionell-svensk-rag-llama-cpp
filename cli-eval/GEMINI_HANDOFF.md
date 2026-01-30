# GEMINI - FIX DESIGNEN

Claude har gjort en fungerande men ful CLI. Din uppgift: gör den snygg.

## Filer

```
/home/dev/ai-server/cli/
├── main.py       ← HUVUDFIL - all kod här (90 rader)
├── client.py     ← WebSocket-klient (RÖR EJ)
├── config.py     ← Config (RÖR EJ)
├── ui.py         ← OANVÄND - kan tas bort eller skrivas om
├── assets.py     ← OANVÄND - kan tas bort eller skrivas om
└── commands.py   ← OANVÄND
```

## Kör CLI

```bash
cd /home/dev/ai-server && python3 -m cli.main
```

## Nuvarande kod (main.py)

```python
#!/usr/bin/env python3
import asyncio
from rich.console import Console
from cli.client import NERDYAIClient

console = Console()

async def main():
    console.clear()
    console.print("[bold bright_cyan]NERDY AI[/]")

    client = NERDYAIClient()
    await client.connect()

    while True:
        user_input = console.input("[bright_cyan]❯[/] ").strip()

        if user_input.lower() in ("/quit", "/exit"):
            break

        console.print("[bold bright_cyan]QWENY:[/] ", end="")
        await client.send_message(user_input, profile="nerdy")

        async for token, stats in client.receive_stream():
            if token:
                print(token, end="", flush=True)
        print()

    await client.close()

asyncio.run(main())
```

## Vad som FUNGERAR

1. `console.input()` - pålitlig input
2. `print(token, end="", flush=True)` - streaming utan buggar
3. `console.print()` - Rich formatting
4. `console.clear()` - rensa skärm

## Vad som INTE fungerar i denna terminal

- `Rich Live()` mode - duplicerar content, skriver över sig själv fel
- `termios` raw input - krånglar
- `prompt_toolkit` - konflikterar med Rich

## Designförslag

Du kan göra vad du vill med designen, men håll dig till:

1. **Input:** `console.input("prompt")` - INTE raw termios
2. **Streaming:** `print(token, end="", flush=True)` - INTE Rich Live
3. **Statisk output:** `console.print()` med Rich formatting är OK

### Exempel på saker du KAN göra:

```python
# Färgad header
console.print(Panel("NERDY AI", style="bold cyan"))

# Färgad prompt
user_input = console.input("[cyan]❯[/] ")

# Formaterad output EFTER streaming är klar
console.print(Panel(full_response, title="QWENY"))

# ASCII art
console.print("""
    ╔═══════════════╗
    ║   NERDY AI    ║
    ╚═══════════════╝
""")
```

### Saker du INTE ska göra:

```python
# INTE Live mode (buggar)
with Live(panel) as live:
    live.update(...)  # <-- DUPLICERAR

# INTE termios (buggar)
tty.setraw(fd)  # <-- KRASCHAR

# INTE prompt_toolkit (konflikterar)
from prompt_toolkit import prompt  # <-- FUNKAR INTE MED RICH
```

## Client API

```python
from cli.client import NERDYAIClient

client = NERDYAIClient()
await client.connect()                           # Anslut
await client.send_message("hej", profile="nerdy")  # Skicka
async for token, stats in client.receive_stream(): # Ta emot
    print(token, end="", flush=True)
await client.close()                             # Stäng
```

## GO!

Gör den snygg. Lägg till ASCII art, färger, vad du vill.
Men använd BARA metoderna som fungerar.
