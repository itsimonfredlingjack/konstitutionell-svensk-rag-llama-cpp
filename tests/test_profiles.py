"""Deprecated tests.

This repository's unit test suite should not depend on a profile system that isn't
present in the Constitutional-AI backend package.

If/when a profile system exists again, add tests alongside its implementation.
"""

import pytest

pytest.skip(
    "Profile system not present in this repo; skipping deprecated tests", allow_module_level=True
)
