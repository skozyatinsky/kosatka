#!/usr/bin/env python3
"""Ищет жёстко записанные пользовательские строки в серверных шаблонах.

Каноническая проверка для `localization.hardcoded_strings_check_path`
(APS-CORE-LOCALIZATION-001) в проектах с базовой локалью на кириллице:
любая кириллица в тексте шаблона или в пользовательском атрибуте — строка
мимо каталога. Выражения `{{ ... }}`, теги `{% ... %}`, комментарии,
`<script>` и `<style>` не проверяются.

Граница метода: латиница не ловится — английская строка в шаблоне проекта с
базовой локалью `ru` останется незамеченной. Строки в Python-коде маршрутов
тоже вне охвата; их проверяет проектный тест.

Постепенный перенос: `--baseline` хранит допустимое число находок на файл.
Проверка падает, если число в файле выросло или появился новый файл с
находками; уменьшение разрешено и подсказывает обновить базу.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE_SUFFIXES = {".html", ".htm", ".jinja", ".jinja2", ".j2"}
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё0-9 .,:;!?«»()—–\-]*")
USER_ATTRIBUTES = ("title", "placeholder", "aria-label", "alt", "label", "value", "data-tooltip")
_SKIP_BLOCKS = (
    re.compile(r"\{#.*?#\}", re.S),
    re.compile(r"<script\b.*?</script>", re.S | re.I),
    re.compile(r"<style\b.*?</style>", re.S | re.I),
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"\{\{.*?\}\}", re.S),
    re.compile(r"\{%.*?%\}", re.S),
)
_ATTRIBUTE_RE = re.compile(r"\s(?P<name>[\w:-]+)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)", re.S)
_TAG_RE = re.compile(r"<[^>]*>", re.S)


def _blank(match: re.Match[str]) -> str:
    """Заменяет пропускаемый фрагмент пробелами, сохраняя переводы строк для номеров."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _user_attributes(tag: str) -> str:
    """Оставляет от тега только пользовательские атрибуты; переводы строк сохраняются."""
    values = [
        match.group("value").replace("\n", " ")
        for match in _ATTRIBUTE_RE.finditer(tag)
        if match.group("name").lower() in USER_ATTRIBUTES
    ]
    return " " + " ".join(values) + " " + "\n" * tag.count("\n")


def find_literals(text: str) -> list[tuple[int, str]]:
    """Возвращает `(номер строки, фрагмент)` для каждой кириллической строки вне каталога."""
    for pattern in _SKIP_BLOCKS:
        text = pattern.sub(_blank, text)
    text = _TAG_RE.sub(lambda match: _user_attributes(match.group(0)), text)
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in CYRILLIC_RE.finditer(line):
            found.append((number, match.group(0).strip()))
    return found


def scan(root: Path, template_dirs: list[str]) -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    for directory in template_dirs:
        base = (root / directory).resolve()
        if not base.is_dir() or root.resolve() not in (base, *base.parents):
            raise SystemExit(f"каталог шаблонов не найден внутри проекта: {directory}")
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() in TEMPLATE_SUFFIXES and path.is_file():
                literals = find_literals(path.read_text(encoding="utf-8", errors="replace"))
                if literals:
                    result[path.relative_to(root.resolve()).as_posix()] = literals
    return result


def compare_with_baseline(found: dict[str, list[tuple[int, str]]], baseline: dict[str, int]) -> tuple[list[str], list[str]]:
    """Ошибки — рост числа находок; заметки — файлы, где строк стало меньше базы."""
    errors, notes = [], []
    for path, literals in sorted(found.items()):
        allowed = int(baseline.get(path, 0))
        if len(literals) > allowed:
            sample = "; ".join(f"{line}: {text}" for line, text in literals[:5])
            errors.append(f"{path}: {len(literals)} строк мимо каталога, допустимо {allowed} — {sample}")
    for path, allowed in sorted(baseline.items()):
        if len(found.get(path, [])) < int(allowed):
            notes.append(f"{path}: осталось {len(found.get(path, []))} из {allowed}, обновите базу (--write-baseline)")
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--templates", action="append", required=True, help="каталог шаблонов относительно --root; можно повторять")
    parser.add_argument("--baseline", help="JSON {путь: допустимое число находок} для постепенного переноса")
    parser.add_argument("--write-baseline", action="store_true", help="записать текущее состояние в --baseline")
    args = parser.parse_args(argv)
    root = Path(args.root)
    found = scan(root, args.templates)
    baseline_path = root / args.baseline if args.baseline else None
    if args.write_baseline:
        if baseline_path is None:
            parser.error("--write-baseline требует --baseline")
        counts = {path: len(items) for path, items in sorted(found.items())}
        baseline_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"база записана: {len(counts)} файлов, {sum(counts.values())} строк")
        return 0
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path and baseline_path.is_file() else {}
    errors, notes = compare_with_baseline(found, baseline)
    for note in notes:
        print(f"NOTE {note}")
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
