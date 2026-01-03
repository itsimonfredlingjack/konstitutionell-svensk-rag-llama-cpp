"""
Slash command handlers for Simons AI CLI
/sven, /kod, /clear, /quit, /agent, /agents
"""
from .client import NERDYAIClient
from .ui import show_status, clear_screen
from .config import (
    MODEL_ARCHITECT, MODEL_CODER,
    MODEL_ARCHITECT_NAME, MODEL_CODER_NAME,
    MODEL_ARCHITECT_DESC, MODEL_CODER_DESC
)

# Available agents (synced with backend)
AVAILABLE_AGENTS = {
    MODEL_ARCHITECT: {
        "name": MODEL_ARCHITECT_NAME,
        "description": MODEL_ARCHITECT_DESC,
        "model": MODEL_ARCHITECT,
    },
    MODEL_CODER: {
        "name": MODEL_CODER_NAME,
        "description": MODEL_CODER_DESC,
        "model": MODEL_CODER,
        "features": ["code_interpreter"],
    },
    "cloud": {
        "name": "CLOUD",
        "description": "Fast cloud API (Grok)",
        "model": "grok-2",
    },
    "nerdy": {
        "name": "NERDY AI",
        "description": "Legal & Compliance Officer",
        "model": "qwen2.5:3b-instruct",
    },
}


async def handle_juridik_command(client: NERDYAIClient, args: str) -> None:
    """
    Sätter temporär system-prompt fokuserad på:
    - If-Then resonemangskedjor
    - Bevisvärdering
    - Strukturerad juridisk analys
    """
    client.set_mode("juridik")
    show_status(
        "[bold bright_cyan]⚖️  IF-THEN MODE ACTIVATED[/] | Focus: Logic chains & Evidence evaluation",
        "success"
    )
    
    # Skicka instruktion till backend som system message
    # Detta kan implementeras genom att lägga till instruktioner i nästa meddelande
    instruction = (
        "Du ska nu fokusera på juridisk analys med:\n"
        "- If-Then resonemangskedjor\n"
        "- Bevisvärdering\n"
        "- Strukturerad juridisk analys\n"
        "- Logisk progression i argumentation"
    )
    
    # Lägg till instruktionen som en del av kontexten
    # För nu sätter vi bara läget, instruktionen kan skickas med nästa meddelande
    # eller implementeras i backend som en system prompt modifierare


async def handle_diarie_command(client: NERDYAIClient, args: str) -> None:
    """
    Aktiverar "Vad saknas?"-läge för diariekontroll.
    Modellen fokuserar på att identifiera saknade dokument/uppgifter.
    """
    client.set_mode("diarie")
    show_status(
        "[bold bright_cyan]📋  GAP ANALYSIS MODE ACTIVATED[/] | Focus: Missing documentation analysis",
        "success"
    )
    
    instruction = (
        "Du ska nu fokusera på diariekontroll och gap analysis:\n"
        "- Identifiera saknade dokument\n"
        "- Identifiera saknade uppgifter\n"
        "- Analysera dokumentationskomplettering\n"
        "- Föreslå åtgärder för att komplettera"
    )


def handle_clear_command() -> None:
    """
    Rensar terminalen men behåller system-prompten.
    Använder Rich's Console.clear()
    """
    clear_screen()
    show_status("[bold bright_cyan]Context buffer cleared[/] | System ready", "info")


async def handle_quit_command(client: NERDYAIClient) -> None:
    """
    Avslutar snyggt:
    - Stänger WebSocket connection
    - Visar avslutningsmeddelande
    - Exit code 0
    """
    show_status("[bold bright_cyan]Terminating session...[/]", "info")
    await client.close()
    show_status("[bold bright_green]Session terminated. Thank you for using NERDY AI![/]", "success")


def handle_agents_command(client: NERDYAIClient) -> None:
    """Lista alla tillgängliga agenter"""
    current = client.get_profile()
    output = "[bold bright_cyan]AVAILABLE AGENTS[/]\n"
    for agent_id, info in AVAILABLE_AGENTS.items():
        marker = "→ " if agent_id == current else "  "
        features = ""
        if "features" in info:
            features = f" [code_interpreter]"
        output += f"{marker}[bold]{agent_id}[/]: {info['description']}{features}\n"
    show_status(output, "info")


def handle_agent_command(client: NERDYAIClient, args: str) -> None:
    """Byt till en annan agent"""
    agent_id = args.strip().lower()

    if not agent_id:
        handle_agents_command(client)
        return

    if agent_id not in AVAILABLE_AGENTS:
        show_status(f"[bold red]Unknown agent: {agent_id}[/]\nUse /agents to see available options", "error")
        return

    agent_info = AVAILABLE_AGENTS[agent_id]
    client.set_profile(agent_id)

    features = ""
    if "features" in agent_info:
        features = " | Features: " + ", ".join(agent_info["features"])

    show_status(
        f"[bold bright_green]AGENT SWITCHED[/] → {agent_info['name']}\n"
        f"Model: {agent_info['model']}{features}",
        "success"
    )


def handle_code_command(client: NERDYAIClient) -> None:
    """Genväg till Devstral 24B med Code Interpreter"""
    handle_agent_command(client, MODEL_CODER)


def handle_sven_command(client: NERDYAIClient) -> None:
    """Genväg till GPT-OSS 20B (Arkitekten)"""
    handle_agent_command(client, MODEL_ARCHITECT)


async def handle_slash_command(client: NERDYAIClient, command: str) -> None:
    """
    Router för slash commands.
    Detekterar och dirigerar till rätt command handler.
    """
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/juridik":
        await handle_juridik_command(client, args)
    elif cmd == "/diarie":
        await handle_diarie_command(client, args)
    elif cmd == "/clear":
        handle_clear_command()
    elif cmd == "/agents":
        handle_agents_command(client)
    elif cmd == "/agent":
        handle_agent_command(client, args)
    elif cmd in ["/kod", "/code", "/coder", "/dev"]:
        handle_code_command(client)
    elif cmd in ["/sven", "/gpt", "/arkitekt", "/think"]:
        handle_sven_command(client)
    elif cmd in ["/quit", "/exit", "/q"]:
        await handle_quit_command(client)
        return True  # Signal to exit REPL loop
    elif cmd == "/help":
        show_status(
            "[bold bright_cyan]AVAILABLE COMMANDS[/]\n"
            f"/sven         - Byt till {MODEL_ARCHITECT_NAME} (Arkitekten)\n"
            f"/kod          - Byt till {MODEL_CODER_NAME} med Code Interpreter\n"
            "/agent <name> - Byt till specifik agent\n"
            "/agents       - Lista alla agenter\n"
            "/juridik      - Aktivera juridiskt analysläge\n"
            "/diarie       - Aktivera gap-analysläge\n"
            "/clear        - Rensa skärmen\n"
            "/quit         - Avsluta CLI",
            "info"
        )
    else:
        show_status(f"Okänt kommando: {cmd}. Använd /help för att se tillgängliga kommandon", "warning")

    return False  # Continue REPL loop
