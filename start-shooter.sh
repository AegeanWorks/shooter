#!/bin/sh
# One-click shooter start (macOS/Linux): ./start-shooter.sh [-- keystone args]
set -eu
cd "$(dirname "$0")"
exec python3 play.py "$@"
