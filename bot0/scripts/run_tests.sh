#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

venv/bin/python -m py_compile \
  main.py \
  label.py \
  core/*.py \
  db/*.py \
  db/repositories/*.py \
  handlers/*.py \
  utils/*.py

venv/bin/python -m unittest discover -s tests -v
