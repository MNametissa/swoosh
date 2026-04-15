#!/usr/bin/env bash
set -e

REPO="MNametissa/swoosh"
INSTALL_DIR="${SWOOSH_INSTALL_DIR:-$HOME/.local/bin}"

echo "Installing Swoosh..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]; }; then
    echo "Error: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi

# Check pipx or pip
if command -v pipx &> /dev/null; then
    echo "Installing with pipx..."
    pipx install swoosh-cli || pipx upgrade swoosh-cli
elif command -v pip3 &> /dev/null; then
    echo "Installing with pip..."
    pip3 install --user swoosh-cli
elif command -v pip &> /dev/null; then
    echo "Installing with pip..."
    pip install --user swoosh-cli
else
    echo "Error: pip or pipx required"
    exit 1
fi

# Verify installation
if command -v swoosh &> /dev/null; then
    echo ""
    echo "Swoosh installed successfully!"
    swoosh --version
else
    echo ""
    echo "Swoosh installed. Add to PATH if not found:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# Check dependencies
echo ""
echo "Checking dependencies..."

if command -v git &> /dev/null; then
    echo "  git: $(git --version | head -1)"
else
    echo "  git: NOT FOUND (required)"
fi

if command -v gh &> /dev/null; then
    echo "  gh: $(gh --version | head -1)"
else
    echo "  gh: NOT FOUND (install: https://cli.github.com)"
fi

if command -v ssh &> /dev/null; then
    echo "  ssh: OK"
else
    echo "  ssh: NOT FOUND (needed for deploy)"
fi

if command -v rsync &> /dev/null; then
    echo "  rsync: OK"
else
    echo "  rsync: NOT FOUND (needed for deploy)"
fi

echo ""
echo "Run 'swoosh doctor' for full system check."
