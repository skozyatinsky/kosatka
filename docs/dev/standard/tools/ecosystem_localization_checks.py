"""Проверки канона локализации парка APS-CORE-LOCALIZATION-002.

Вынесено из `ecosystem_project_validation.py`, чтобы правило оставалось
коротким. Сам `validate_localization_canon` с объявлением диагностик живёт там.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ecosystem_validation_common import (
    LOCALIZATION_CANON_RULE,
    existing_relative,
    finding,
    load_json,
)
from rule_traceability_types import RuleFinding

LOCALE_COOKIE_NAME = "ui_locale"
RESOLUTION_STEPS = ("user_choice", "user_profile", "accept_language", "fallback")
WEB_FORMS = {"web_pwa"}
# `{name}` (format) и `{{name}}` (i18next, Jinja-подобные движки).
PLACEHOLDER_RE = re.compile(r"\{\{?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}?\}")


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def flatten_catalog(data: dict[str, Any], prefix: str = "") -> tuple[dict[str, Any], list[str]]:
    """Плоский вид каталога: вложенный `{"nav": {"sales": ..}}` и `{"nav.sales": ..}` равны.

    Возвращает ключи с путём через точку и список путей, встретившихся дважды
    (например, плоский `a.b` рядом с вложенным `a: {b: ..}`).
    """
    flat: dict[str, Any] = {}
    collisions: list[str] = []
    for key, value in data.items():
        path = f"{prefix}{key}"
        nested = flatten_catalog(value, f"{path}.") if isinstance(value, dict) else ({path: value}, [])
        for nested_key, nested_value in nested[0].items():
            if nested_key in flat:
                collisions.append(nested_key)
            flat[nested_key] = nested_value
        collisions.extend(nested[1])
    return flat, collisions


def load_catalog(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Читает каталог и отвергает дубли ключей, которые `json.loads` молча схлопывает."""
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"), object_pairs_hook=_reject_duplicates)
    except _DuplicateKeyError as exc:
        return None, f"ключ повторяется: {exc}"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "каталог не является JSON-объектом"
    flat, collisions = flatten_catalog(data)
    if collisions:
        return None, f"ключ повторяется после разворота точек: {sorted(set(collisions))}"
    return flat, None


def catalog_value_findings(locale: str, catalog: dict[str, Any]) -> list[RuleFinding]:
    bad = sorted(key for key, value in catalog.items() if not isinstance(value, str) or not value.strip())
    if not bad:
        return []
    return [finding(
        "LOCALIZATION_CATALOG_INVALID", LOCALIZATION_CANON_RULE,
        "Значение перевода должно быть непустой строкой: пустая строка — это скрытый пропуск перевода",
        locale=locale, keys=bad,
    )]


def placeholder_findings(base: dict[str, Any], locale: str, catalog: dict[str, Any]) -> list[RuleFinding]:
    """Переведённая строка обязана сохранить те же подстановки, что и базовая."""
    broken = []
    for key, base_value in base.items():
        value = catalog.get(key)
        if not isinstance(value, str) or not isinstance(base_value, str):
            continue
        if set(PLACEHOLDER_RE.findall(value)) != set(PLACEHOLDER_RE.findall(base_value)):
            broken.append(key)
    if not broken:
        return []
    return [finding(
        "LOCALIZATION_PLACEHOLDERS_MISMATCH", LOCALIZATION_CANON_RULE,
        "Подстановки в переводе не совпадают с базовой локалью",
        locale=locale, keys=sorted(broken),
    )]


def switching_findings(profile: dict[str, Any], runtime_forms: list[Any]) -> list[RuleFinding]:
    supported = profile.get("supported_locales") if isinstance(profile.get("supported_locales"), list) else []
    switching = profile.get("switching")
    if len(supported) < 2 and switching is None:
        return []
    if not isinstance(switching, dict):
        return [finding("LOCALIZATION_SWITCHING_INVALID", LOCALIZATION_CANON_RULE, "При нескольких локалях профиль объявляет switching")]
    findings: list[RuleFinding] = []
    order = switching.get("resolution_order") if isinstance(switching.get("resolution_order"), list) else []
    canonical = [step for step in RESOLUTION_STEPS if step in order]
    if order != canonical or not order or order[0] != "user_choice" or order[-1] != "fallback":
        findings.append(finding(
            "LOCALIZATION_SWITCHING_INVALID", LOCALIZATION_CANON_RULE,
            "Порядок выбора локали: user_choice → [user_profile] → [accept_language] → fallback",
            resolution_order=order,
        ))
    if WEB_FORMS & set(runtime_forms):
        if switching.get("storage") != "cookie" or switching.get("cookie_name") != LOCALE_COOKIE_NAME:
            findings.append(finding(
                "LOCALIZATION_SWITCHING_INVALID", LOCALIZATION_CANON_RULE,
                f"Веб-интерфейс хранит выбор языка в cookie {LOCALE_COOKIE_NAME}",
                storage=switching.get("storage"), cookie_name=switching.get("cookie_name"),
            ))
    if switching.get("preserves_query_string") is not True:
        findings.append(finding(
            "LOCALIZATION_SWITCHING_INVALID", LOCALIZATION_CANON_RULE,
            "Переключение языка возвращает на ту же страницу с той же строкой запроса",
        ))
    return findings


def unreviewed_findings(root: Path, profile: dict[str, Any], key_sets: dict[str, set[str]]) -> list[RuleFinding]:
    """Учёт непроверенного машинного перевода.

    Файл `unreviewed_path` — `{"<локаль>": ["ключ", ...]}`. Непустой список —
    предупреждение; локаль из `release_ready_locales` с непустым списком —
    ошибка: объявлять язык готовым для клиентов можно только после вычитки.
    """
    supported = profile.get("supported_locales") if isinstance(profile.get("supported_locales"), list) else []
    if len(supported) < 2:
        return []
    path = existing_relative(root, profile.get("unreviewed_path"))
    if path is None:
        return [finding(
            "LOCALIZATION_UNREVIEWED_LEDGER_INVALID", LOCALIZATION_CANON_RULE,
            "При нескольких локалях нужен файл учёта непроверенного перевода (может быть {})",
            path=profile.get("unreviewed_path"),
        )]
    raw, _error = load_json(path)
    if not isinstance(raw, dict) or any(not isinstance(value, list) for value in raw.values()):
        return [finding("LOCALIZATION_UNREVIEWED_LEDGER_INVALID", LOCALIZATION_CANON_RULE, "Учёт непроверенного перевода: ожидался объект {локаль: [ключи]}", path=str(profile.get("unreviewed_path")))]
    ready = set(profile.get("release_ready_locales") or [])
    findings: list[RuleFinding] = []
    if not ready <= set(supported):
        findings.append(finding("LOCALIZATION_UNREVIEWED_LEDGER_INVALID", LOCALIZATION_CANON_RULE, "release_ready_locales должны входить в supported_locales", release_ready_locales=sorted(ready)))
    for locale, keys in sorted(raw.items()):
        unknown = sorted(set(map(str, keys)) - key_sets.get(locale, set()))
        if unknown:
            findings.append(finding("LOCALIZATION_UNREVIEWED_LEDGER_INVALID", LOCALIZATION_CANON_RULE, "В учёте непроверенного перевода есть ключи, которых нет в каталоге", locale=locale, keys=unknown))
        if not keys:
            continue
        if locale in ready:
            findings.append(finding("LOCALIZATION_UNREVIEWED_RELEASE_LOCALE", LOCALIZATION_CANON_RULE, "Локаль объявлена готовой для клиентов, но в ней есть невычитанный перевод", locale=locale, count=len(keys)))
        else:
            findings.append(finding("LOCALIZATION_TRANSLATION_UNREVIEWED", LOCALIZATION_CANON_RULE, "Машинный перевод ждёт вычитки носителем", severity="WARNING", locale=locale, count=len(keys)))
    return findings
