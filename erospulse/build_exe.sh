#!/usr/bin/env bash
# ============================================================
#  build_exe.sh
#  Builds a native standalone executable from source, on macOS
#  or Linux (an .app bundle on macOS, an ELF binary on Linux).
#
#  Requirements: Python 3.10+ installed and available as
#  "python3" on PATH. Nothing else needs to be pre-installed:
#  this script installs PyInstaller itself, and points it at the
#  vendor/ folder already bundled with the project so that
#  requests/urllib3/etc. get packaged into the executable without
#  any extra "pip install" of your own.
#
#  Run from the project root:
#      chmod +x build_exe.sh   (first time only)
#      ./build_exe.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo "=== Installing PyInstaller ==="
python3 -m pip install --upgrade pyinstaller

echo
echo "=== Building ErosPulse ==="
export PYTHONPATH="$(pwd)/vendor:$PYTHONPATH"
python3 -m PyInstaller ErosPulse.spec --noconfirm

echo
echo "============================================================"
echo " Done. Your executable is at: dist/ErosPulse"
echo "============================================================"
