#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx nao encontrado. Instalando..."
  python3 -m pip install --user pipx
  python3 -m pipx ensurepath
fi

if pipx list 2>/dev/null | grep -q "viper"; then
  echo "Removendo instalacao antiga de viper..."
  pipx uninstall viper || true
fi

echo "Instalando viper via pipx a partir de: ${ROOT_DIR}"
pipx install --force "${ROOT_DIR}"

echo "Instalado. Teste com: viper --help"
