#!/bin/bash
# Script simples para executar o Anki Automation
# Uso: ./run-simple.sh [argumentos]

cd "$(dirname "$0")"
source venv/bin/activate
python main.py "$@"
deactivate
