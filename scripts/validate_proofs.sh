#!/bin/bash

# Script to validate Lean proofs via Lake
set -euo pipefail

PROOFS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/proofs"

if [ ! -d "$PROOFS_DIR" ]; then
    echo "Error: Proofs directory '$PROOFS_DIR' not found."
    exit 1
fi

# Locate lean/lake: prefer elan-managed toolchain, fall back to PATH
if [ -f "$HOME/.elan/bin/lean" ]; then
    export PATH="$HOME/.elan/bin:$PATH"
fi

if ! command -v lake &> /dev/null; then
    echo "Error: 'lake' not found. Install Lean 4 via:"
    echo "  brew install elan-init && elan default stable"
    exit 1
fi

echo "Lean $(lean --version)"
echo "Lake $(lake --version)"
echo ""
echo "Building Lean proofs in '$PROOFS_DIR'..."
cd "$PROOFS_DIR"
lake build

echo ""
echo "All proofs verified successfully."
