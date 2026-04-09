#!/bin/bash

# Script to validate Lean proofs
# Ensure Lean is installed and available in PATH

set -euo pipefail

# Check if Lean is installed
if ! command -v lean &> /dev/null; then
    echo "Error: Lean theorem prover is not installed or not in PATH."
    echo "Please install Lean from https://leanprover.github.io/ and ensure it is in your PATH."
    exit 1
fi

# Directory containing the Lean proofs
PROOFS_DIR="proofs"

# Check if proofs directory exists
if [ ! -d "$PROOFS_DIR" ]; then
    echo "Error: Proofs directory '$PROOFS_DIR' not found."
    exit 1
fi

# Validate each proof file
echo "Validating Lean proofs in '$PROOFS_DIR'..."
for proof_file in "$PROOFS_DIR"/*.lean; do
    echo "Validating $proof_file..."
    if lean --run "$proof_file" &> /dev/null; then
        echo "✓ $proof_file is valid"
    else
        echo "✗ $proof_file failed validation"
        exit 1
    fi
done

echo "All proofs validated successfully!"

exit 0