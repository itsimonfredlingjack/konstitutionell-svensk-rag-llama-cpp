#!/usr/bin/env python3
"""
Seed Constitutional Examples - RetICL Implementation

Creates a ChromaDB collection 'constitutional_examples' with few-shot examples
for in-context learning. Examples are retrieved dynamically based on user queries
to improve model tone and legal compliance.

Usage:
    python seed_constitutional_examples.py
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import chromadb
from app.services.config_service import get_config_service
from app.services.embedding_service import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Example data structure (to be populated from document or manually)
CONSTITUTIONAL_EXAMPLES = [
    {
        "mode": "EVIDENCE",
        "user": "Vad säger GDPR om rätt att bli bortglömd?",
        "assistant": {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt GDPR artikel 17 har data subjects rätt att begära radering av personuppgifter under vissa förutsättningar. Detta kallas 'rätt att bli bortglömd' (right to be forgotten).",
            "kallor": [
                {
                    "doc_id": "gdpr_art17",
                    "chunk_id": "art17_1",
                    "citat": "Artikel 17 - Rätt till radering",
                    "loc": "GDPR Art. 17",
                }
            ],
            "fakta_utan_kalla": [],
        },
    },
    {
        "mode": "EVIDENCE",
        "user": "Vilka är kraven för att behandla personuppgifter enligt GDPR?",
        "assistant": {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt GDPR artikel 6 krävs en laglig grund för behandling av personuppgifter. De sex lagliga grunderna är: samtycke, kontraktsfullgörelse, rättslig förpliktelse, skydd av vitala intressen, allmänintresse och berättigat intresse.",
            "kallor": [
                {
                    "doc_id": "gdpr_art6",
                    "chunk_id": "art6_1",
                    "citat": "Artikel 6 - Laglig grund för behandling",
                    "loc": "GDPR Art. 6.1",
                }
            ],
            "fakta_utan_kalla": [],
        },
    },
    {
        "mode": "EVIDENCE",
        "user": "Vad säger lagen om semester?",
        "assistant": {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera.",
            "kallor": [],
            "fakta_utan_kalla": [],
        },
    },
    {
        "mode": "ASSIST",
        "user": "Kan du förklara vad GDPR är?",
        "assistant": {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "GDPR (General Data Protection Regulation) är EU:s dataskyddsförordning som trädde i kraft 2018. Den reglerar hur personuppgifter får behandlas och ger individer rättigheter över sina data. I Sverige implementeras GDPR genom Dataskyddsförordningen (2018:218).",
            "kallor": [
                {
                    "doc_id": "gdpr_intro",
                    "chunk_id": "intro_1",
                    "citat": "GDPR är EU:s dataskyddsförordning",
                    "loc": "GDPR Introduction",
                }
            ],
            "fakta_utan_kalla": [
                "GDPR trädde i kraft 2018",
                "Implementeras i Sverige genom Dataskyddsförordningen (2018:218)",
            ],
        },
    },
    {
        "mode": "ASSIST",
        "user": "Hur fungerar offentlighetsprincipen?",
        "assistant": {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "Offentlighetsprincipen är en grundläggande princip i svensk förvaltning som innebär att allmänheten har rätt att ta del av handlingar hos myndigheter. Detta regleras i Tryckfrihetsförordningen (1949:105). Principen gäller med vissa undantag för sekretessbelagda uppgifter.",
            "kallor": [
                {
                    "doc_id": "tf_1949_105",
                    "chunk_id": "tf_2kap",
                    "citat": "Offentlighetsprincipen",
                    "loc": "TF 2 kap",
                }
            ],
            "fakta_utan_kalla": [
                "Regleras i Tryckfrihetsförordningen (1949:105)",
                "Gäller med undantag för sekretessbelagda uppgifter",
            ],
        },
    },
    {
        "mode": "ASSIST",
        "user": "Vad är skillnaden mellan SFS och prop?",
        "assistant": {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "SFS (Svensk författningssamling) är den officiella samlingen av alla författningar som trätt i kraft i Sverige. Prop (proposition) är ett regeringsförslag som skickas till riksdagen för beslut. En prop kan bli en SFS om den antas av riksdagen.",
            "kallor": [],
            "fakta_utan_kalla": [
                "SFS är officiell samling av författningar",
                "Prop är regeringsförslag till riksdagen",
                "Prop kan bli SFS om den antas",
            ],
        },
    },
]


def seed_constitutional_examples():
    """
    Seed ChromaDB collection with constitutional examples.

    Creates 'constitutional_examples' collection and indexes examples
    with embeddings of the 'user' field (question).
    """
    config = get_config_service()
    embedding_service = get_embedding_service(config)

    # Initialize ChromaDB
    chromadb_path = config.chromadb_path
    collection_name = "constitutional_examples"

    logger.info(f"Connecting to ChromaDB at: {chromadb_path}")
    client = chromadb.PersistentClient(path=chromadb_path)

    # Get or create collection
    try:
        collection = client.get_collection(name=collection_name)
        logger.info(f"Using existing collection: {collection_name} ({collection.count()} examples)")
        # Clear existing examples for re-seeding
        collection.delete()
        logger.info("Cleared existing examples")
    except Exception:
        collection = client.create_collection(
            name=collection_name,
            metadata={"description": "Constitutional AI few-shot examples for RetICL"},
        )
        logger.info(f"Created new collection: {collection_name}")

    # Process examples
    logger.info(f"Processing {len(CONSTITUTIONAL_EXAMPLES)} examples")

    ids = []
    documents = []  # User questions for embedding
    metadatas = []  # Full example JSON

    for i, example in enumerate(CONSTITUTIONAL_EXAMPLES):
        example_id = f"example_{i+1}"
        user_question = example["user"]
        full_example = json.dumps(example, ensure_ascii=False)

        ids.append(example_id)
        documents.append(user_question)  # Embed the question
        metadatas.append(
            {
                "mode": example["mode"],
                "user": user_question,
                "example_json": full_example,  # Store full JSON for retrieval
            }
        )

    # Generate embeddings for user questions
    logger.info("Generating embeddings for examples...")
    embeddings = embedding_service.embed(documents)

    # Add to collection
    logger.info(f"Adding {len(ids)} examples to collection...")
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    # Verify
    final_count = collection.count()
    logger.info(f"✅ Successfully seeded {final_count} constitutional examples")

    return {
        "collection": collection_name,
        "examples_count": final_count,
        "chromadb_path": chromadb_path,
    }


if __name__ == "__main__":
    result = seed_constitutional_examples()
    print(json.dumps(result, indent=2))
