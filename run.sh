#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Activar virtualenv
source "$DIR/venv/bin/activate"

# Workaround para libmpv.so.2 (necesario para Flet desktop en Linux)
export LD_LIBRARY_PATH="$DIR/.local/lib:$LD_LIBRARY_PATH"

# Ejecutar
python "$DIR/main.py"
