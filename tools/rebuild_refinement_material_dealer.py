#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENCHANT_DB = ROOT / "db/re/item_enchant.yml"
DEALER = ROOT / "npc/custom/refinement_material_dealer.txt"
AUDIT_DIR = ROOT / "npc/custom/refinement_material_dealer"
AUDIT_CSV = AUDIT_DIR / "item_enchant_materials.csv"
SUMMARY_JSON = AUDIT_DIR / "item_enchant_materials_summary.json"

ENCHANT_PRICE = 20_000
PAGE_SIZE = 35

# Preserve the existing refinement-material inventory and prices exactly.
REFINEMENT_ITEMS = [
    (7619, 10_000),
    (7620, 10_000),
    (6241, 30_000),
    (6240, 30_000),
    (6225, 100_000),
    (6226, 100_000),
    (1000333, 50_000),
    (1000334, 50_000),
    (1000335, 200_000),
    (1000336, 200_000),
    (1000371, 800_000),
    (1000369, 800_000),
]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_item_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    paths = sorted((ROOT / "db/re").glob("item_db_*.yml"))
    paths += sorted((ROOT / "db/import").glob("item_db*.yml"))
    for path in paths:
        data = load_yaml(path)
        for row in data.get("Body", []) or []:
            if not isinstance(row, dict):
                continue
            aegis = row.get("AegisName")
            item_id = row.get("Id")
            if isinstance(aegis, str) and isinstance(item_id, int):
                index[aegis] = {
                    "item_id": item_id,
                    "aegis_name": aegis,
                    "display_name": str(row.get("Name") or aegis),
                    "item_type": str(row.get("Type") or ""),
                    "source_file": str(path.relative_to(ROOT)),
                }
    return index


def classify_material_context(path: tuple[str, ...]) -> str:
    if "Reset" in path:
        return "reset"
    if "PerfectEnchants" in path:
        return "perfect"
    if "Upgrades" in path:
        return "upgrade"
    return "normal"


def collect_material_usage() -> dict[str, dict[str, Any]]:
    data = load_yaml(ENCHANT_DB)
    usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "occurrences": 0,
            "reset": 0,
            "normal": 0,
            "perfect": 0,
            "upgrade": 0,
            "enchant_ids": set(),
            "targets": set(),
        }
    )

    for enchant in data.get("Body", []) or []:
        if not isinstance(enchant, dict):
            continue
        enchant_id = enchant.get("Id")
        targets = set((enchant.get("TargetItems") or {}).keys())

        def walk(node: Any, path: tuple[str, ...] = ()) -> None:
            if isinstance(node, dict):
                material = node.get("Material")
                if isinstance(material, str):
                    entry = usage[material]
                    context = classify_material_context(path)
                    entry["occurrences"] += 1
                    entry[context] += 1
                    if isinstance(enchant_id, int):
                        entry["enchant_ids"].add(enchant_id)
                    entry["targets"].update(targets)
                for key, value in node.items():
                    walk(value, path + (str(key),))
            elif isinstance(node, list):
                for value in node:
                    walk(value, path)

        walk(enchant)

    return usage


def quote_script_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def emit_setarray(lines: list[str], var: str, values: list[Any], chunk_size: int = 50) -> None:
    for offset, group in enumerate(chunks(values, chunk_size)):
        start = offset * chunk_size
        rendered = []
        for value in group:
            rendered.append(quote_script_string(value) if isinstance(value, str) else str(value))
        lines.append(f"\tsetarray {var}[{start}],")
        for row in chunks(rendered, 10):
            ending = "," if row is not chunks(rendered, 10)[-1] else ";"
            # Avoid relying on list identity by fixing the ending afterward below.
            lines.append("\t\t" + ",".join(row) + ",")
        lines[-1] = lines[-1][:-1] + ";"


def short_label(name: str, limit: int = 26) -> str:
    clean = " ".join(name.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def build() -> None:
    item_index = load_item_index()
    usage = collect_material_usage()
    missing = sorted(set(usage) - set(item_index))
    if missing:
        raise SystemExit(f"Unresolved material Aegis names: {missing}")

    rows: list[dict[str, Any]] = []
    for aegis, stats in usage.items():
        item = item_index[aegis]
        rows.append(
            {
                **item,
                "price": ENCHANT_PRICE,
                "occurrences": stats["occurrences"],
                "reset_uses": stats["reset"],
                "normal_uses": stats["normal"],
                "perfect_uses": stats["perfect"],
                "upgrade_uses": stats["upgrade"],
                "enchant_database_ids": ";".join(map(str, sorted(stats["enchant_ids"]))),
                "target_item_count": len(stats["targets"]),
            }
        )

    by_name = sorted(rows, key=lambda row: (row["display_name"].casefold(), row["item_id"]))
    pages = chunks(by_name, PAGE_SIZE)
    item_page: dict[int, int] = {}
    for page_index, page in enumerate(pages):
        for row in page:
            item_page[row["item_id"]] = page_index

    by_id = sorted(rows, key=lambda row: row["item_id"])

    lines: list[str] = [
        "//===== rAthena Script =======================================",
        "//= Refinement Material Dealer - Complete Enchant Materials",
        "//===== Description: =========================================",
        "//= Preserves the original refinement-material stock and adds",
        "//= every unique Material consumed by db/re/item_enchant.yml.",
        "//= Enchant materials are alphabetical, paged, and searchable",
        "//= by Item ID. Generated by tools/rebuild_refinement_material_dealer.py.",
        "//============================================================",
        "",
        "prontera,160,187,4\tscript\tRefinement Material Dealer#custom\t53,{",
        "\twhile (1) {",
        "\t\tclear;",
        "\t\tmes \"[Refinement Material Dealer]\";",
        "\t\tmes \"Refinement supplies and every material currently consumed by the Item Enchant database are available here.\";",
        "\t\tnext;",
        f"\t\tswitch(select(\"Refinement materials ({len(REFINEMENT_ITEMS)}):Find enchant material by Item ID:Browse enchant materials ({len(rows)}):Price and coverage information:Close\")) {{",
        "\t\tcase 1:",
        "\t\t\tclose2;",
        "\t\t\tcallshop \"RMD_REFINE\",1;",
        "\t\t\tend;",
        "\t\tcase 2:",
        "\t\t\tcallfunc \"F_RMD_SEARCH\";",
        "\t\t\tbreak;",
        "\t\tcase 3:",
        "\t\t\tcallfunc \"F_RMD_BROWSE\";",
        "\t\t\tbreak;",
        "\t\tcase 4:",
        "\t\t\tmes \"[Refinement Material Dealer]\";",
        f"\t\t\tmes \"Enchant-material price: {ENCHANT_PRICE:,} Zeny each.\";",
        f"\t\t\tmes \"Coverage: {len(rows)} unique Material entries referenced by Common, Perfect, Upgrade, or Reset operations in db/re/item_enchant.yml.\";",
        "\t\t\tmes \"Target equipment and enchant-result cards are not included unless the database consumes them as a Material.\";",
        "\t\t\tnext;",
        "\t\t\tbreak;",
        "\t\tdefault:",
        "\t\t\tclose;",
        "\t\t}",
        "\t}",
        "\tend;",
        "",
        "OnInit:",
        f"\t$@RMD_EnchantCount = {len(rows)};",
        f"\t$@RMD_PageCount = {len(pages)};",
    ]

    emit_setarray(lines, "$@RMD_PageShop$", [f"RMD_E{i+1:02d}" for i in range(len(pages))])
    page_labels = [
        f"Page {i+1}: {short_label(page[0]['display_name'])} - {short_label(page[-1]['display_name'])}"
        for i, page in enumerate(pages)
    ]
    emit_setarray(lines, "$@RMD_PageLabel$", page_labels, 30)
    emit_setarray(lines, "$@RMD_ItemId", [row["item_id"] for row in by_id])
    emit_setarray(lines, "$@RMD_ItemPage", [item_page[row["item_id"]] for row in by_id])
    lines += ["\tend;", "}", ""]

    lines += [
        "function\tscript\tF_RMD_SEARCH\t{",
        "\tmes \"[Enchant Material Search]\";",
        "\tmes \"Enter the numeric Item ID of a material.\";",
        "\tinput .@item_id;",
        "\tif (.@item_id <= 0 || getiteminfo(.@item_id, ITEMINFO_ID) != .@item_id) {",
        "\t\tmes \"[Enchant Material Search]\";",
        "\t\tmes \"That is not a valid server Item ID.\";",
        "\t\treturn;",
        "\t}",
        "\t.@low = 0;",
        "\t.@high = $@RMD_EnchantCount - 1;",
        "\t.@found = -1;",
        "\twhile (.@low <= .@high) {",
        "\t\t.@mid = (.@low + .@high) / 2;",
        "\t\tif ($@RMD_ItemId[.@mid] == .@item_id) {",
        "\t\t\t.@found = .@mid;",
        "\t\t\tbreak;",
        "\t\t}",
        "\t\tif ($@RMD_ItemId[.@mid] < .@item_id)",
        "\t\t\t.@low = .@mid + 1;",
        "\t\telse",
        "\t\t\t.@high = .@mid - 1;",
        "\t}",
        "\tmes \"[Enchant Material Search]\";",
        "\tif (.@found < 0) {",
        "\t\tmes mesitemlink(.@item_id) + \" is not consumed as a Material by the current Item Enchant database.\";",
        "\t\treturn;",
        "\t}",
        "\t.@page = $@RMD_ItemPage[.@found];",
        "\tmes mesitemlink(.@item_id);",
        f"\tmes \"Price: {ENCHANT_PRICE:,} Zeny each.\";",
        "\tmes \"Shop: \" + $@RMD_PageLabel$[.@page];",
        "\tnext;",
        "\tif (select(\"Open exact shop page:Back\") == 1) {",
        "\t\tclose2;",
        "\t\tcallshop($@RMD_PageShop$[.@page],1);",
        "\t\tend;",
        "\t}",
        "\treturn;",
        "}",
        "",
        "function\tscript\tF_RMD_BROWSE\t{",
        "\tmes \"[Enchant Material Browser]\";",
        "\tmes \"Materials are sorted by their displayed item name.\";",
        "\tnext;",
    ]
    browse_options = page_labels + ["Back"]
    lines.append("\tswitch(select(" + quote_script_string(":".join(browse_options)) + ")) {")
    for i in range(len(pages)):
        lines += [
            f"\tcase {i+1}:",
            "\t\tclose2;",
            f"\t\tcallshop \"RMD_E{i+1:02d}\",1;",
            "\t\tend;",
        ]
    lines += [f"\tcase {len(pages)+1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]

    refine_stock = ",".join(f"{item_id}:{price}" for item_id, price in REFINEMENT_ITEMS)
    lines.append(f"-1,shop\tRMD_REFINE\t-1,{refine_stock}")
    for i, page in enumerate(pages):
        stock = ",".join(f"{row['item_id']}:{ENCHANT_PRICE}" for row in page)
        lines.append(f"-1,shop\tRMD_E{i+1:02d}\t-1,{stock}")
    lines.append("")

    DEALER.write_text("\n".join(lines), encoding="utf-8")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "item_id",
        "aegis_name",
        "display_name",
        "item_type",
        "price",
        "occurrences",
        "reset_uses",
        "normal_uses",
        "perfect_uses",
        "upgrade_uses",
        "enchant_database_ids",
        "target_item_count",
        "source_file",
        "shop_page",
    ]
    with AUDIT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda value: value["item_id"]):
            output = dict(row)
            output["shop_page"] = item_page[row["item_id"]] + 1
            writer.writerow({key: output[key] for key in fields})

    summary = {
        "source": "db/re/item_enchant.yml",
        "unique_materials": len(rows),
        "material_references": sum(row["occurrences"] for row in rows),
        "reset_references": sum(row["reset_uses"] for row in rows),
        "normal_references": sum(row["normal_uses"] for row in rows),
        "perfect_references": sum(row["perfect_uses"] for row in rows),
        "upgrade_references": sum(row["upgrade_uses"] for row in rows),
        "enchant_material_price": ENCHANT_PRICE,
        "page_size": PAGE_SIZE,
        "shop_pages": len(pages),
        "original_refinement_items_preserved": len(REFINEMENT_ITEMS),
        "unresolved_materials": [],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    build()
