#!/usr/bin/env bash
# ======================================================================
# run.sh — Канонический запуск iskinosfera-orca (FILE_AND_FOLDER_STANDARD §2.1)
# Паттерн «Правило одного клика»: строго без параметров, foreground, exec make run
# ======================================================================
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ "$#" -ne 0 ]]; then
  echo "Использование: ./run.sh" >&2
  exit 2
fi

# Подмена процесса: передача управления в Makefile без порождения висячих shell-обёрток
exec make run
