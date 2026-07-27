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
MAX_SELECT_LENGTH = 240
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


def load_materials() -> set[str] | None:
    if not SOURCE.exists():
        return None
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


def parse_stock(raw: str) -> dict[int, int]:
    result: dict[int, int] = {}
    for token in raw.split(","):
        item_id, price = token.split(":", 1)
        result[int(item_id)] = int(price)
    return result


def parse_array(text: str, variable: str) -> list[int]:
    pattern = re.compile(
        rf"setarray {re.escape(variable)}\[(\d+)\],\s*(.*?);",
        re.S,
    )
    values: dict[int, int] = {}
    for match in pattern.finditer(text):
        offset = int(match.group(1))
        body_values = [int(value) for value in re.findall(r"\b\d+\b", match.group(2))]
        for index, value in enumerate(body_values):
            absolute = offset + index
            assert absolute not in values, f"Overlapping {variable} array index {absolute}"
            values[absolute] = value
    assert values, f"No values found for {variable}"
    assert sorted(values) == list(range(max(values) + 1)), f"Gaps in {variable} array"
    return [values[index] for index in range(max(values) + 1)]


def assert_balanced(text: str) -> None:
    # Strip line comments and quoted strings before delimiter checks.
    cleaned_lines = []
    for line in text.splitlines():
        if "//" in line:
            line = line.split("//", 1)[0]
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '""', cleaned)
    for opener, closer in [("{", "}"), ("(", ")")]:
        depth = 0
        for char in cleaned:
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                assert depth >= 0, f"Unexpected {closer}"
        assert depth == 0, f"Unbalanced {opener}{closer}: depth={depth}"


def main() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    with AUDIT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert "-1,shop" not in text, "Invalid -1,shop declaration remains"
    assert_balanced(text)

    source_materials = load_materials()
    audit_aegis = {row["aegis_name"] for row in rows}
    if source_materials is not None:
        assert source_materials == audit_aegis, (
            f"Material set mismatch: source={len(source_materials)} audit={len(audit_aegis)}"
        )

    audit_ids = [int(row["item_id"]) for row in rows]
    assert len(audit_ids) == len(set(audit_ids)) == 369
    assert all(int(row["price"]) == EXPECTED_PRICE for row in rows)

    shop_pattern = re.compile(r"^-\tshop\t(RMD_(?:REFINE|E\d{2}))\t-1,(.+)$", re.M)
    shop_defs = {name: parse_stock(stock) for name, stock in shop_pattern.findall(text)}
    expected_names = {"RMD_REFINE", *(f"RMD_E{i:02d}" for i in range(1, 12))}
    assert set(shop_defs) == expected_names, f"Shop definitions mismatch: {sorted(shop_defs)}"
    assert shop_defs["RMD_REFINE"] == EXPECTED_REFINEMENT

    page_ids: list[int] = []
    for page in range(1, 12):
        name = f"RMD_E{page:02d}"
        stock = shop_defs[name]
        assert 1 <= len(stock) <= 35, f"{name} has {len(stock)} items"
        assert all(price == EXPECTED_PRICE for price in stock.values())
        page_ids.extend(stock)
    assert len(page_ids) == len(set(page_ids)) == 369
    assert set(page_ids) == set(audit_ids)

    calls = re.findall(r'callshop\s+"(RMD_(?:REFINE|E\d{2}))"\s*,\s*1', text)
    assert set(calls) == expected_names, f"callshop targets mismatch: {sorted(set(calls))}"

    dispatcher = re.search(
        r"function\tscript\tF_RMD_OPEN_PAGE\t\{(?P<body>.*?)\n\}",
        text,
        re.S,
    )
    assert dispatcher, "Missing F_RMD_OPEN_PAGE"
    mappings = re.findall(
        r"case\s+(\d+):\s*callshop\s+\"(RMD_E\d{2})\",1;",
        dispatcher.group("body"),
        re.S,
    )
    assert mappings == [(str(i), f"RMD_E{i + 1:02d}") for i in range(11)], mappings

    select_strings = re.findall(r'select\("([^"\\]*(?:\\.[^"\\]*)*)"\)', text)
    assert select_strings, "No select menus found"
    lengths = [len(value) for value in select_strings]
    assert max(lengths) <= MAX_SELECT_LENGTH, f"select too long: {max(lengths)}"
    for menu in select_strings:
        options = menu.split(":")
        assert all(option.strip() for option in options), f"Empty menu option: {menu}"

    page_menus = [menu for menu in select_strings if menu.startswith("Page ")]
    assert len(page_menus) == 3, f"Expected 3 page submenus, got {len(page_menus)}"
    for menu in page_menus:
        options = menu.split(":")
        assert options[-1] == "Back"
        assert all(option.startswith("Page ") for option in options[:-1])
    assert [len(menu.split(":")) for menu in page_menus] == [5, 5, 4]

    group_menu = next(menu for menu in select_strings if menu.startswith("Pages 1-4"))
    assert group_menu.split(":") == ["Pages 1-4", "Pages 5-8", "Pages 9-11", "Back"]

    ids = parse_array(text, "$@RMD_ItemId")
    pages = parse_array(text, "$@RMD_ItemPage")
    assert ids == sorted(audit_ids), f"Search ID array mismatch: {len(ids)}"
    assert len(pages) == len(ids) == 369
    assert all(0 <= page <= 10 for page in pages)

    expected_page_by_id = {
        int(row["item_id"]): int(row["shop_page"]) - 1
        for row in rows
    }
    assert pages == [expected_page_by_id[item_id] for item_id in ids]

    function_defs = re.findall(r"^function\tscript\t([A-Za-z0-9_]+)\t\{", text, re.M)
    assert len(function_defs) == len(set(function_defs))
    expected_functions = {
        "F_RMD_SEARCH",
        "F_RMD_OPEN_PAGE",
        "F_RMD_BROWSE",
        "F_RMD_BROWSE_GROUP_1",
        "F_RMD_BROWSE_GROUP_2",
        "F_RMD_BROWSE_GROUP_3",
    }
    assert set(function_defs) == expected_functions

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["unique_materials"] == 369
    assert summary["shop_pages"] == 11
    assert summary["browse_groups"] == 3
    assert summary["maximum_select_length"] == max(lengths)
    assert summary["unresolved_materials"] == []

    print("REFINEMENT MATERIAL DEALER VALIDATION PASSED")
    print(f"unique enchant materials: {len(audit_ids)}")
    print(f"shop pages: {len(page_ids) // 35 + (1 if len(page_ids) % 35 else 0)}")
    print(f"registered hidden shops: {len(shop_defs)}")
    print(f"maximum select length: {max(lengths)}")
    print("page submenu option counts: 5, 5, 4")
    print("static page dispatcher mappings: 11")
    print(f"refinement materials preserved: {len(EXPECTED_REFINEMENT)}")
    print(f"enchant material unit price: {EXPECTED_PRICE}")


if __name__ == "__main__":
    main()
