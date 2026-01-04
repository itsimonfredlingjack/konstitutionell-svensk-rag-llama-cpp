#!/usr/bin/env python3
"""Quick status check for harvest operation"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cli.brain import get_brain

brain = get_brain()

if not brain.collection:
    print("❌ ChromaDB not available!")
    sys.exit(1)

count = brain.collection.count()
target = 100_000
remaining = max(0, target - count)
progress = (count / target) * 100 if target > 0 else 0

print("=" * 70)
print("HARVEST STATUS")
print("=" * 70)
print(f"Current documents: {count:,}")
print(f"Target:            {target:,}")
print(f"Remaining:         {remaining:,}")
print(f"Progress:          {progress:.1f}%")
print("=" * 70)

if count >= target:
    print("✅ TARGET REACHED!")
else:
    print(f"⏳ Need {remaining:,} more documents")
