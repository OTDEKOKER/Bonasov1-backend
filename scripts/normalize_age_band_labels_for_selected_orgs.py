#!/usr/bin/env python3
"""Normalize aggregate disaggregate age-band keys for selected organizations.

Default scope: project 2, Makgabaneng + Bonepwa+subs org IDs.
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import sys
from decimal import Decimal
from typing import Any

import django


DEFAULT_ORG_IDS = [
    5,  # Makgabaneng
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    122,
    123,
    124,
    125,
    126,
    127,
    128,
    130,
    131,
    132,
    133,
    134,
    135,
    136,
    175,
    176,
    177,
    178,
    179,
    180,
]


def normalize_age_band_label(label: str) -> str:
    raw = str(label or "").strip()
    if not raw:
        return raw

    simple = re.sub(r"[_\s]+", " ", raw).strip().lower()
    if simple in {"ayp", "ayp 10 24", "ayp (10-24)", "ayp(10-24)"}:
        return "AYP (10-24)"

    m_range = re.match(r"^(\d{1,2})\s*[-–]\s*(\d{1,2})$", raw)
    if m_range:
        start = int(m_range.group(1))
        end = int(m_range.group(2))
        if start >= 65 or end >= 65:
            return "65+"
        return f"{start}-{end}"

    m_plus = re.match(r"^(\d{1,2})\s*\+$", raw)
    if m_plus:
        start = int(m_plus.group(1))
        if start >= 65:
            return "65+"
        return f"{start}+"

    m_single = re.match(r"^(\d{1,2})$", raw)
    if m_single:
        value = int(m_single.group(1))
        if value >= 65:
            return "65+"

    return raw


def _is_probable_age_key(key: str) -> bool:
    key = str(key or "").strip()
    if not key:
        return False
    compact = key.replace("_", " ").lower().strip()
    if compact in {"ayp", "ayp 10 24", "ayp (10-24)", "ayp(10-24)"}:
        return True
    if re.match(r"^\d{1,2}\s*[-–]\s*\d{1,2}$", key):
        return True
    if re.match(r"^\d{1,2}\s*\+$", key):
        return True
    if re.match(r"^\d{1,2}$", key):
        return True
    return False


def _merge_values(existing: Any, incoming: Any) -> Any:
    if existing is None:
        return incoming

    numeric_types = (int, float, Decimal)
    if isinstance(existing, numeric_types) and isinstance(incoming, numeric_types):
        return existing + incoming

    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(existing)
        for k, v in incoming.items():
            merged[k] = _merge_values(merged.get(k), v)
        return merged

    return incoming


def normalize_structure(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            new_key = normalize_age_band_label(key) if _is_probable_age_key(str(key)) else key
            new_nested = normalize_structure(nested)
            if new_key in result:
                result[new_key] = _merge_values(result[new_key], new_nested)
            else:
                result[new_key] = new_nested
        return result

    if isinstance(value, list):
        return [normalize_structure(item) for item in value]

    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=int, default=2)
    parser.add_argument("--org-ids", nargs="*", type=int, default=DEFAULT_ORG_IDS)
    parser.add_argument("--apply", action="store_true", help="Persist changes (default is dry-run)")
    args = parser.parse_args()

    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

    from aggregates.models import Aggregate  # noqa: WPS433

    qs = Aggregate.objects.filter(project_id=args.project_id, organization_id__in=args.org_ids)

    total = qs.count()
    changed = 0
    unchanged = 0

    for aggregate in qs.iterator(chunk_size=500):
        current = aggregate.value if isinstance(aggregate.value, dict) else aggregate.value
        normalized = normalize_structure(current)
        if normalized != current:
            changed += 1
            if args.apply:
                aggregate.value = normalized
                aggregate.save(update_fields=["value", "updated_at"])
        else:
            unchanged += 1

    mode = "APPLY" if args.apply else "DRY_RUN"
    print(
        f"{mode} total={total} changed={changed} unchanged={unchanged} "
        f"project={args.project_id} org_count={len(args.org_ids)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
