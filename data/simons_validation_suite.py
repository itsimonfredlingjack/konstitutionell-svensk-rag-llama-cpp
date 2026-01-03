"""
Simons Validation Suite - Baserat på FAKTISKA användningsmönster
Genererad från observation av daglig användning.
"""

# Tier 1: Dagliga Operations (10x/dag)
DAILY_OPS = [
    "Hur går det?",  # Expects: GPU stats automatically
    "Vad är GPU temp?",
    "Vilka modeller kör?",
    "Git status",
    "Mina Linear issues",
    "Läs /mnt/config.json",
    "Hitta propositioner om AI",
    "n8n workflow status",
    "Show recent commits",
    "Constitutional AI query logs"
]

# Tier 2: Utvecklingsarbete (5x/dag)
DEV_WORK = [
    "Skapa n8n workflow för email automation",
    "Debug Constitutional AI timeout issue",
    "Optimize ChromaDB query performance",
    "Load Devstral och unload planner",
    "Deploy changes till production",
    "Create Linear issue: Timeout in RAG pipeline",
    "Search Hugging Face för Swedish models",
    "Git diff senaste ändringarna",
    "Läs error logs från igår",
    "Test webhook endpoint"
]

# Tier 3: Research och Planning (2x/dag)
RESEARCH = [
    "Vilka är bästa embeddings för Nordic languages?",
    "Search papers om RAG optimization",
    "How do other legal databases handle Swedish case law?",
    "Calculate cost savings från local models vs API",
    "Design cascade pipeline för Constitutional AI v2",
    "Hugging Face trends för reasoning models",
    "Find datasets för Swedish parliamentary proceedings",
    "Optimize VRAM usage för multi-model deployment",
    "n8n best practices för AI workflows"
]

# Emergency Scenarios - Speed over explanation
EMERGENCY = [
    "claude.fredlingautomation.dev är ner - NU",
    "n8n webhook failar för alla requests - quick",
    "Constitutional AI returnerar gibberish - debug fast",
    "VRAM maxed och system frozen - help"
]

# Code-Switching Tests (Svenska/Engelska fluently)
CODE_SWITCHING = [
    ("Hur många issues har jag?", "svenska"),
    ("What's the GPU temperature?", "engelska"),
    ("Can you läsa config.yaml och förklara loadbalancer settings?", "mixed"),
]

# Multi-System Debugging Chains
DEBUGGING_CHAINS = {
    "Constitutional AI inte svarar": [
        "Check if model is loaded",
        "Check VRAM usage",
        "Check ChromaDB status",
        "Read recent logs"
    ],
    "n8n workflow broke": [
        "Check n8n execution logs",
        "Git diff för workflow changes",
        "Check external APIs",
        "Verify webhooks"
    ],
    "System laggar": [
        "nvidia-smi check",
        "List running processes",
        "Check loaded models",
        "Suggest unloading"
    ]
}

# All tests combined
ALL_TESTS = DAILY_OPS + DEV_WORK + RESEARCH + EMERGENCY

def get_test_batch(tier: str = "daily") -> list:
    """Get test queries by tier"""
    return {
        "daily": DAILY_OPS,
        "dev": DEV_WORK,
        "research": RESEARCH,
        "emergency": EMERGENCY,
        "all": ALL_TESTS
    }.get(tier, DAILY_OPS)
