#!/usr/bin/env bash
# One-click start for Linux / macOS
set -e
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python app.py
