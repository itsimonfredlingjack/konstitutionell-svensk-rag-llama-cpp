#!/usr/bin/env python3
"""
Agent Lightning Training Script för Cascade Pipeline
=====================================================
Tränar multi-agent cascade (Planner→Coder→Reviewer) med
reinforcement learning via Microsoft Agent Lightning.

Användning:
    # Enkel testkörning
    python scripts/train_cascade_agent.py --test

    # Full träning
    python scripts/train_cascade_agent.py --data data/training_data.jsonl --epochs 10

    # Med Agent Lightning server (för full RL)
    agl train --agent CascadeLitAgent --data data/training_data.jsonl
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_training_data(path: str) -> list[dict[str, Any]]:
    """Ladda training data från JSONL (stödjer flera format)"""
    tasks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                # Stöd för olika fältnamn
                question = (
                    data.get("prompt") or data.get("instruction") or data.get("question") or ""
                )
                expected = (
                    data.get("completion") or data.get("output") or data.get("expected") or ""
                )
                if question:
                    tasks.append(
                        {
                            "question": question,
                            "expected_answer": expected,
                        }
                    )
    return tasks


async def test_single_rollout():
    """Testa en enskild rollout"""
    from app.services.cascade_lit_agent import cascade_lit_agent

    print("\n" + "=" * 60)
    print("Testing single cascade rollout")
    print("=" * 60)

    task = {
        "question": "Skriv en Python-funktion som validerar email-adresser med regex",
        "expected_answer": "import re\ndef validate_email",
    }

    print(f"\nTask: {task['question']}")
    print("\nRunning cascade...")

    start = time.time()
    reward = await cascade_lit_agent.training_rollout_async(
        task=task, rollout_id="test-001", resources=None
    )
    duration = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"RESULT: reward = {reward:.2f}")
    print(f"Duration: {duration:.1f}s")
    print(f"{'=' * 60}")

    return reward


async def run_training_epoch(
    tasks: list[dict], epoch: int, verbose: bool = True
) -> dict[str, float]:
    """Kör en träningsepoch"""
    from app.services.cascade_lit_agent import cascade_lit_agent

    rewards = []
    errors = 0

    for i, task in enumerate(tasks):
        rollout_id = f"epoch{epoch}-task{i}"

        if verbose:
            print(f"\n[{i + 1}/{len(tasks)}] {task['question'][:60]}...")

        try:
            reward = await cascade_lit_agent.training_rollout_async(
                task=task, rollout_id=rollout_id, resources=None
            )
            rewards.append(reward)

            if verbose:
                print(f"  -> reward: {reward:.2f}")

        except Exception as e:
            print(f"  -> ERROR: {e}")
            errors += 1
            rewards.append(-1.0)

    return {
        "epoch": epoch,
        "avg_reward": sum(rewards) / len(rewards) if rewards else 0,
        "max_reward": max(rewards) if rewards else 0,
        "min_reward": min(rewards) if rewards else 0,
        "errors": errors,
        "tasks": len(tasks),
    }


async def main_training_loop(
    data_path: str, epochs: int, sample_size: int = 0, verbose: bool = True
):
    """Huvudträningsloop"""
    print("\n" + "=" * 60)
    print("Agent Lightning Training - Cascade Pipeline")
    print("=" * 60)

    # Ladda data
    tasks = load_training_data(data_path)
    print(f"\nLoaded {len(tasks)} training tasks from {data_path}")

    if sample_size > 0 and sample_size < len(tasks):
        import random

        tasks = random.sample(tasks, sample_size)
        print(f"Sampled {sample_size} tasks for training")

    # Training log
    log_path = Path("data/training_log.jsonl")
    log_path.parent.mkdir(exist_ok=True)

    all_results = []

    for epoch in range(1, epochs + 1):
        print(f"\n{'=' * 60}")
        print(f"EPOCH {epoch}/{epochs}")
        print(f"{'=' * 60}")

        start = time.time()
        results = await run_training_epoch(tasks, epoch, verbose)
        duration = time.time() - start

        results["duration_sec"] = duration
        all_results.append(results)

        # Logga resultat
        with open(log_path, "a") as f:
            f.write(json.dumps(results) + "\n")

        print(f"\nEpoch {epoch} Summary:")
        print(f"  Average reward: {results['avg_reward']:.2f}")
        print(f"  Max reward: {results['max_reward']:.2f}")
        print(f"  Min reward: {results['min_reward']:.2f}")
        print(f"  Errors: {results['errors']}")
        print(f"  Duration: {duration:.1f}s")

    # Final summary
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    if all_results:
        avg_rewards = [r["avg_reward"] for r in all_results]
        print(f"Epochs: {len(all_results)}")
        print(f"Overall avg reward: {sum(avg_rewards) / len(avg_rewards):.2f}")
        print(f"Best epoch reward: {max(avg_rewards):.2f}")
        print(f"Training log: {log_path}")

    return all_results


def create_sample_tasks() -> list[dict]:
    """Skapa sample tasks för test"""
    return [
        {
            "question": "Skriv en Python REST API endpoint som returnerar användardata",
            "expected_answer": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/users')",
        },
        {
            "question": "Skapa en React-komponent för en sökruta med debounce",
            "expected_answer": "import { useState, useEffect } from 'react'\nfunction SearchBox",
        },
        {
            "question": "Implementera en cache-decorator i Python med TTL",
            "expected_answer": "from functools import wraps\nimport time\ndef cache_with_ttl",
        },
    ]


async def main():
    parser = argparse.ArgumentParser(description="Train Cascade Agent with Agent Lightning")
    parser.add_argument("--test", action="store_true", help="Run single test rollout")
    parser.add_argument(
        "--data", type=str, default="data/training_data.jsonl", help="Training data path"
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of epochs")
    parser.add_argument("--sample", type=int, default=0, help="Sample N tasks (0=all)")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")

    args = parser.parse_args()

    if args.test:
        reward = await test_single_rollout()
        return 0 if reward > 0 else 1

    # Kolla om data finns
    if not Path(args.data).exists():
        print(f"ERROR: Training data not found at {args.data}")
        print("\nCreating sample tasks for demo...")

        # Spara sample tasks
        sample = create_sample_tasks()
        Path(args.data).parent.mkdir(exist_ok=True)
        with open(args.data, "w") as f:
            for task in sample:
                f.write(
                    json.dumps({"instruction": task["question"], "output": task["expected_answer"]})
                    + "\n"
                )
        print(f"Created {len(sample)} sample tasks at {args.data}")

    # Kör träning
    await main_training_loop(
        data_path=args.data, epochs=args.epochs, sample_size=args.sample, verbose=not args.quiet
    )

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
