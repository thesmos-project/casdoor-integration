#!/usr/bin/env python3
"""Distinguish an absent version tag from registry/network/authentication errors."""
import os
from pathlib import Path
import sys

tag = os.environ["VERSION_TAG"]
lines = Path(sys.argv[1]).read_text().splitlines()
absent = {tag + ": not found", "ERROR: " + tag + ": not found"}
if not any(line.strip() in absent or "manifest unknown" in line.lower() or "manifest_unknown" in line.lower()
           or "no such manifest" in line.lower() for line in lines):
    print("Version tag lookup failed without confirming absence; publication is blocked.", file=sys.stderr)
    sys.exit(2)
print("Version tag is absent; publication can continue.")
