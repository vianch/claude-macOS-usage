#!/bin/bash
# Build Claude Usage Monitor as a macOS .app bundle
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Create/activate venv if needed
if [ ! -d ".venv" ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Generating app icon..."
python scripts/generate_icon.py

echo "==> Building .app bundle with py2app..."
python setup.py py2app

echo ""
echo "==> Build complete!"
echo "    App location: dist/Claude Usage Monitor.app"
echo ""
echo "    To install, run:"
echo "      cp -r 'dist/Claude Usage Monitor.app' /Applications/"
echo ""
echo "    To run directly:"
echo "      open 'dist/Claude Usage Monitor.app'"
