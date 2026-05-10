# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import sys
from pathlib import Path

# Lambda modules use bare imports (e.g. `from config import Config`).
# Add src/memory_handler so those imports resolve without a package prefix.
_SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC / "memory_handler"))
# Add src/ for cert_rotator package imports (cert_rotator.handler).
sys.path.insert(0, str(_SRC))
