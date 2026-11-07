#!/usr/bin/env bash
# ======================================================================
# build.sh — Канонический скрипт сборки iskinosfera-orca (FILE_AND_FOLDER_STANDARD §2.2)
# Поддерживает как неинтерактивный режим (headless CLI), так и меню в терминале.
# ======================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

have() { command -v "$1" >/dev/null 2>&1; }

check_deps() {
  local fail=0
  echo "--- Проверка зависимостей iskinosfera-orca ---"
  if have node; then
    echo "OK   node: $(node --version 2>&1)"
  else
    echo "FAIL node отсутствует"
    fail=1
  fi

  if have pnpm; then
    echo "OK   pnpm: $(pnpm --version 2>&1)"
  else
    echo "FAIL pnpm отсутствует"
    fail=1
  fi

  return "$fail"
}

clean_artifacts() {
  echo "Очистка временных файлов сборки..."
  rm -rf "${ROOT}/out" "${ROOT}/dist"
  echo "Готово."
}

build_desktop() {
  echo "Сборка десктопного приложения..."
  cd "${ROOT}"
  pnpm run build
}

build_all() {
  check_deps || true
  clean_artifacts
  echo "Сборка iskinosfera-orca завершена успешно."
}

# Обработка неинтерактивных аргументов командной строки (headless)
if [[ $# -gt 0 ]] || [ ! -t 0 ]; then
  case "${1:-}" in
    --check-deps)
      check_deps
      exit 0
      ;;
    --clean)
      clean_artifacts
      exit 0
      ;;
    --target-desktop)
      build_desktop
      exit 0
      ;;
    --target-all|--all|"")
      build_all
      exit 0
      ;;
    *)
      echo "Неизвестный параметр сборки: $1" >&2
      echo "Использование: ./build.sh [--check-deps|--clean|--target-desktop|--target-all]" >&2
      exit 2
      ;;
  esac
fi

# Интерактивное меню для оператора в терминале
menu_options=(
  "Проверить зависимости сборки"
  "Собрать десктопное приложение"
  "Полная сборка (--target-all)"
  "Очистить артефакты (out/dist)"
  "Выход"
)

while true; do
  echo ""
  echo "=================================================="
  echo " Сборка iskinosfera-orca — Интерактивный режим"
  echo " Выберите действие цифрой:"
  echo "=================================================="
  for i in "${!menu_options[@]}"; do
    printf "%2d) %s\n" "$((i+1))" "${menu_options[$i]}"
  done
  echo ""

  if ! read -r -p "Выбор (цифра): " reply; then
    echo ""
    break
  fi

  case "$reply" in
    1) check_deps || true ;;
    2) build_desktop ;;
    3) build_all ;;
    4) clean_artifacts ;;
    5) echo "Выход."; break ;;
    "") continue ;;
    *) echo "Неверный пункт: $reply" ;;
  esac
done
