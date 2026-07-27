#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "db/re/item_enchant.yml"
SCRIPT = ROOT / "npc/custom/refinement_material_dealer.txt"
AUDIT = ROOT / "npc/custom/refinement_material_dealer/item_enchant_materials.csv"
SUMMARY = ROOT / "npc/custom/refinement_material_dealer/item_enchant_materials_summary.json"
EXPECTED_PRICE = 20_000
EXPECTED_REFINEMENT = {
    7619: 10_000,
    7620: 10_000,
    6241: 30_000,
    6240: 30_000,
    6225: 100_000,
    6226: 100_000,
    1000333: 50_000,
    1000334: 50_000,
    1000335: 200_000,
    1000336: 200_000,
    1000371: 800_000,
    1000369: 800_000,
}


def load_materials() -> set[str]:
    data = yaml.safe_load(SOURCE.read_text(encoding="utf-8")) or {}
    result: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            material = node.get("Material")
            if isinstance(material, str):
                result.add(material)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return result


def parse_stock(line: str) -> dict[int, int]:
    stock = line.split("\t-1,", 1)[1]
    result: dict[int, int] = {}
    for token in stock.split(","):
        item_id, price = token.split(":")
        result[int(item_id)] = int(price)
    return result


def main() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    with AUDIT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    source_materials = load_materials()
    audit_aegis = {row["aegis_name"] for row in rows}
    audit_ids = [int(row["item_id"]) for row in rows]
    assert source_materials == audit_aegis, (
        f"Material set mismatch: source={len(source_materials)} audit={len(audit_aegis)}"
    )
    assert len(audit_ids) == len(set(audit_ids)) == 369
    assert all(int(row["price"]) == EXPECTED_PRICE for row in rows)

    shop_lines = [line for line in text.splitlines() if line.startswith("-1,shop\tRMD_E")]
    assert len(shop_lines) == 11
    shop_ids: list[int] = []
    for line in shop_lines:
        stock = parse_stock(line)
        assert 1 <= len(stock) <= 35
        assert all(price == EXPECTED_PRICE for price in stock.values())
        shop_ids.extend(stock)
    assert len(shop_ids) == len(set(shop_ids)) == 369
    assert set(shop_ids) == set(audit_ids)

    refine_line = next(line for line in text.splitlines() if line.startswith("-1,shop\tRMD_REFINE"))
    assert parse_stock(refine_line) == EXPECTED_REFINEMENT

    # Search arrays must contain every ID once and be sorted for binary search.
    id_block = re.search(
        r"setarray \$@RMD_ItemId\[0\],(?P<body>.*?)setarray \$@RMD_ItemPage\[0\],",
        text,
        re.S,
    )
    assert id_block
    ids = [int(value) for value in re.findall(r"\b\d+\b", id_block.group("body"))]
    # Remove the numeric offsets from subsequent setarray declarations.
    ids = [value for value in ids if value not in {50, 100, 150, 200, 250, 300, 350}]
    assert ids == sorted(audit_ids), f"Search ID array mismatch: {len(ids)}"

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["unique_materials"] == 369
    assert summary["shop_pages"] == 11
    assert summary["unresolved_materials"] == []

    max_shop_line = max(len(line) for line in shop_lines)
    browse_start = text.index('function\tscript\tF_RMD_BROWSE')
    browse_switch = re.search(r'switch\(select\("(.*?)"\)\)', text[browse_start:], re.S)
    assert browse_switch
    max_menu_option = max(len(option) for option in browse_switch.group(1).split(':'))

    print("PASS")
    print(f"unique enchant materials: {len(audit_ids)}")
    print(f"item-enchant material references: {summary['material_references']}")
    print(f"shop pages: {len(shop_lines)}")
    print(f"maximum items per page: {max(len(parse_stock(line)) for line in shop_lines)}")
    print(f"maximum hidden-shop line length: {max_shop_line}")
    print(f"maximum browser menu option length: {max_menu_option}")
    print(f"original refinement materials preserved: {len(EXPECTED_REFINEMENT)}")
    print(f"enchant material unit price: {EXPECTED_PRICE}")


if __name__ == "__main__":
    main()
