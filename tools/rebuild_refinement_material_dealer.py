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
BROWSE_GROUP_SIZE = 4
MAX_SELECT_LENGTH = 240

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
        rendered = [quote_script_string(v) if isinstance(v, str) else str(v) for v in group]
        lines.append(f"\tsetarray {var}[{start}],")
        rendered_rows = chunks(rendered, 10)
        for row_index, row in enumerate(rendered_rows):
            suffix = ";" if row_index == len(rendered_rows) - 1 else ","
            lines.append("\t\t" + ",".join(row) + suffix)


def short_label(name: str, limit: int = 20) -> str:
    clean = " ".join(name.split()).replace(":", "-")
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def make_menu(options: list[str], context: str) -> str:
    if any(":" in option for option in options):
        raise SystemExit(f"Internal colon in {context} option: {options}")
    menu = ":".join(options)
    if len(menu) > MAX_SELECT_LENGTH:
        raise SystemExit(f"{context} menu too long: {len(menu)}")
    return menu


def build() -> None:
    rows: list[dict[str, Any]] = []
    if ENCHANT_DB.exists():
        item_index = load_item_index()
        usage = collect_material_usage()
        missing = sorted(set(usage) - set(item_index))
        if missing:
            raise SystemExit(f"Unresolved material Aegis names: {missing}")

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
    elif AUDIT_CSV.exists():
        with AUDIT_CSV.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                rows.append(
                    {
                        "item_id": int(raw["item_id"]),
                        "aegis_name": raw["aegis_name"],
                        "display_name": raw["display_name"],
                        "item_type": raw["item_type"],
                        "source_file": raw["source_file"],
                        "price": ENCHANT_PRICE,
                        "occurrences": int(raw["occurrences"]),
                        "reset_uses": int(raw["reset_uses"]),
                        "normal_uses": int(raw["normal_uses"]),
                        "perfect_uses": int(raw["perfect_uses"]),
                        "upgrade_uses": int(raw["upgrade_uses"]),
                        "enchant_database_ids": raw["enchant_database_ids"],
                        "target_item_count": int(raw["target_item_count"]),
                    }
                )
    else:
        raise SystemExit("Neither db/re/item_enchant.yml nor the existing material audit CSV is available")

    by_name = sorted(rows, key=lambda row: (row["display_name"].casefold(), row["item_id"]))
    pages = chunks(by_name, PAGE_SIZE)
    item_page: dict[int, int] = {}
    for page_index, page in enumerate(pages):
        for row in page:
            item_page[row["item_id"]] = page_index

    by_id = sorted(rows, key=lambda row: row["item_id"])
    page_labels = [
        f"Page {i + 1} - {short_label(page[0]['display_name'])} to {short_label(page[-1]['display_name'])}"
        for i, page in enumerate(pages)
    ]
    page_groups = chunks(list(range(len(pages))), BROWSE_GROUP_SIZE)

    main_menu = make_menu(
        [
            f"Refinement materials ({len(REFINEMENT_ITEMS)})",
            "Find enchant material by Item ID",
            f"Browse enchant materials ({len(rows)})",
            "Price and coverage information",
            "Close",
        ],
        "main",
    )

    lines: list[str] = [
        "//===== rAthena Script =======================================",
        "//= Refinement Material Dealer - Complete Enchant Materials",
        "//===== Description: =========================================",
        "//= Preserves the original refinement-material stock and adds",
        "//= every unique Material consumed by db/re/item_enchant.yml.",
        "//= Menus are split into safe groups; no select option contains",
        "//= an internal colon and every select string stays below 240 chars.",
        "//= Generated by tools/rebuild_refinement_material_dealer.py.",
        "//============================================================",
        "",
        "prontera,160,187,4\tscript\tRefinement Material Dealer#custom\t53,{",
        "\twhile (1) {",
        "\t\tclear;",
        "\t\tmes \"[Refinement Material Dealer]\";",
        "\t\tmes \"Refinement supplies and all materials currently consumed by the Item Enchant database are available here.\";",
        "\t\tnext;",
        f"\t\tswitch(select({quote_script_string(main_menu)})) {{",
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
        f"\t\t\tmes \"Coverage: {len(rows)} unique materials from Common, Perfect, Upgrade, and Reset entries.\";",
        "\t\t\tmes \"The list is alphabetical and divided into small shop pages for reliable client display.\";",
        "\t\t\tnext;",
        "\t\t\tbreak;",
        "\t\tcase 5:",
        "\t\t\tclose;",
        "\t\t}",
        "\t}",
        "\tend;",
        "",
        "OnInit:",
        f"\t$@RMD_EnchantCount = {len(rows)};",
        f"\t$@RMD_PageCount = {len(pages)};",
    ]

    emit_setarray(lines, "$@RMD_PageLabel$", page_labels, 30)
    emit_setarray(lines, "$@RMD_ItemId", [row["item_id"] for row in by_id])
    emit_setarray(lines, "$@RMD_ItemPage", [item_page[row["item_id"]] for row in by_id])
    lines += ["\tend;", "}", ""]

    lines += [
        "function\tscript\tF_RMD_SEARCH\t{",
        "\tmes \"[Enchant Material Search]\";",
        "\tmes \"Enter the numeric Item ID.\";",
        "\tinput .@item_id;",
        "\tif (.@item_id <= 0) {",
        "\t\tmes \"[Enchant Material Search]\";",
        "\t\tmes \"The Item ID must be greater than zero.\";",
        "\t\tnext;",
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
        "\t\tmes \"Item ID \" + .@item_id + \" is not sold by this dealer.\";",
        "\t\tnext;",
        "\t\treturn;",
        "\t}",
        "\t.@page = $@RMD_ItemPage[.@found];",
        "\tmes mesitemlink(.@item_id);",
        f"\tmes \"Price: {ENCHANT_PRICE:,} Zeny each.\";",
        "\tmes \"Location: \" + $@RMD_PageLabel$[.@page];",
        "\tnext;",
        "\tif (select(\"Open shop page:Back\") == 1) {",
        "\t\tcallfunc \"F_RMD_OPEN_PAGE\", .@page;",
        "\t\tend;",
        "\t}",
        "\treturn;",
        "}",
        "",
        "function\tscript\tF_RMD_OPEN_PAGE\t{",
        "\t.@page = getarg(0, -1);",
        "\tclose2;",
        "\tswitch (.@page) {",
    ]
    for page_index in range(len(pages)):
        lines += [
            f"\tcase {page_index}:",
            f"\t\tcallshop \"RMD_E{page_index + 1:02d}\",1;",
            "\t\tend;",
        ]
    lines += ["\t}", "\tend;", "}", ""]

    group_options = [
        f"Pages {group[0] + 1}-{group[-1] + 1}" if len(group) > 1 else f"Page {group[0] + 1}"
        for group in page_groups
    ] + ["Back"]
    group_menu = make_menu(group_options, "browse group")
    lines += [
        "function\tscript\tF_RMD_BROWSE\t{",
        "\twhile (1) {",
        "\t\tclear;",
        "\t\tmes \"[Enchant Material Browser]\";",
        "\t\tmes \"Materials are sorted alphabetically. Choose a page group.\";",
        "\t\tnext;",
        f"\t\tswitch(select({quote_script_string(group_menu)})) {{",
    ]
    for group_index in range(len(page_groups)):
        lines += [
            f"\t\tcase {group_index + 1}:",
            f"\t\t\tcallfunc \"F_RMD_BROWSE_GROUP_{group_index + 1}\";",
            "\t\t\tbreak;",
        ]
    lines += [
        f"\t\tcase {len(page_groups) + 1}:",
        "\t\t\treturn;",
        "\t\t}",
        "\t}",
        "\treturn;",
        "}",
        "",
    ]

    for group_index, group in enumerate(page_groups):
        submenu_options = [page_labels[page_index] for page_index in group] + ["Back"]
        submenu = make_menu(submenu_options, f"browse submenu {group_index + 1}")
        lines += [
            f"function\tscript\tF_RMD_BROWSE_GROUP_{group_index + 1}\t{{",
            "\tmes \"[Enchant Material Browser]\";",
            "\tmes \"Choose the shop page to open.\";",
            "\tnext;",
            f"\tswitch(select({quote_script_string(submenu)})) {{",
        ]
        for option_index, page_index in enumerate(group):
            lines += [
                f"\tcase {option_index + 1}:",
                f"\t\tcallfunc \"F_RMD_OPEN_PAGE\", {page_index};",
                "\t\tend;",
            ]
        lines += [
            f"\tcase {len(group) + 1}:",
            "\t\treturn;",
            "\t}",
            "\treturn;",
            "}",
            "",
        ]

    refine_stock = ",".join(f"{item_id}:{price}" for item_id, price in REFINEMENT_ITEMS)
    lines.append(f"-\tshop\tRMD_REFINE\t-1,{refine_stock}")
    for page_index, page in enumerate(pages):
        stock = ",".join(f"{row['item_id']}:{ENCHANT_PRICE}" for row in page)
        lines.append(f"-\tshop\tRMD_E{page_index + 1:02d}\t-1,{stock}")
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
        "browse_groups": len(page_groups),
        "maximum_select_length": max(
            len(main_menu),
            len(group_menu),
            *(len(make_menu([page_labels[i] for i in group] + ["Back"], "summary")) for group in page_groups),
        ),
        "original_refinement_items_preserved": len(REFINEMENT_ITEMS),
        "unresolved_materials": [],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    build()
