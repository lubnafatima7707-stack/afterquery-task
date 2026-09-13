#!/bin/bash
set -euo pipefail

cp "$(dirname "$0")/nvm_store.py" /app/nvm_store.py
chmod 0644 /app/nvm_store.py
