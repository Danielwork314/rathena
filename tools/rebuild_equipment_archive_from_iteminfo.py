#!/usr/bin/env python3
"""Rebuild Equipment Archive from active Renewal DB and the real client itemInfo.lua."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

PAGE_SIZE = 40
MAX_PAGE_OPTIONS = 8
CATEGORIES = [
    ("W", "Weapons"),
    ("H", "Headgear"),
    ("A", "Armor"),
    ("S", "Shields"),
    ("G", "Garments"),
    ("F", "Shoes"),
    ("X", "Accessories"),
]
LOW_BANDS = [
    ("A", "Req. Lv 0-29", 0, 29, 100000),
    ("B", "Req. Lv 30-59", 30, 59, 100000),
    ("C", "Req. Lv 60-79", 60, 79, 100000),
    ("D", "Req. Lv 80-99", 80, 99, 100000),
]
HIGH_BANDS = [
    ("A", "Lv 100-129", 100, 129, 200000),
    ("B", "Lv 130-159", 130, 159, 500000),
    ("C", "Lv 160-199", 160, 199, 1000000),
    ("D", "Lv 200+", 200, None, 2000000),
]
INVALID_TEXT = {"", "(null)", "null", "unknown", "unknown item"}
KNOWN_RUNTIME_BAD_IDS = {490098, 490376, 490411, 490418, 490430, 490436}
KNOWN_RUNTIME_BAD_RESOURCES = {"Record_Mage2_TW", "Ring_of_Pazuzu"}
ENTRY_RE = re.compile(rb"(?m)^\s*\[(\d+)\]\s*=\s*\{")
ASCII_FIELD_RE = {
    name: re.compile(rb"(?m)^\s*" + name.encode("ascii") + rb'\s*=\s*"([^"\r\n]*)"')
    for name in ("identifiedDisplayName", "identifiedResourceName", "unidentifiedDisplayName", "unidentifiedResourceName")
}
INT_FIELD_RE = {
    name: re.compile(rb"(?m)^\s*" + name.encode("ascii") + rb"\s*=\s*(\d+)")
    for name in ("slotCount", "ClassNum")
}
BOOL_FIELD_RE = re.compile(rb"(?m)^\s*costume\s*=\s*(true|false)")
SERVER_FIELD_RE = re.compile(rb'(?m)^\s*Server\s*=\s*"([^"\r\n]*)"')


def parse_iteminfo(path: Path) -> tuple[dict[int, dict], str]:
    raw = path.read_bytes()
    marks = [(int(m.group(1)), m.start()) for m in ENTRY_RE.finditer(raw)]
    if len(marks) < 1000:
        raise ValueError("The supplied itemInfo.lua is a loader or incomplete file; fewer than 1000 IDs were found.")
    result: dict[int, dict] = {}
    for index, (item_id, start) in enumerate(marks):
        end = marks[index + 1][1] if index + 1 < len(marks) else len(raw)
        block = raw[start:end]
        row: dict[str, object] = {}
        for field, pattern in ASCII_FIELD_RE.items():
            match = pattern.search(block)
            row[field] = match.group(1).decode("latin1") if match else None
        for field, pattern in INT_FIELD_RE.items():
            match = pattern.search(block)
            row[field] = int(match.group(1)) if match else None
        match = BOOL_FIELD_RE.search(block)
        row["costume"] = match.group(1) == b"true" if match else None
        match = SERVER_FIELD_RE.search(block)
        row["Server"] = match.group(1).decode("ascii", errors="replace") if match else ""
        result[item_id] = row
    return result, hashlib.sha256(raw).hexdigest()


def standard_category(item: dict) -> str | None:
    item_type = item.get("Type")
    locations = set((item.get("Locations") or {}).keys())
    if item_type == "Weapon":
        return "Weapons"
    if item_type != "Armor":
        return None
    if locations & {"Head_Top", "Head_Mid", "Head_Low"}:
        return "Headgear"
    if "Armor" in locations:
        return "Armor"
    if "Left_Hand" in locations:
        return "Shields"
    if "Garment" in locations:
        return "Garments"
    if "Shoes" in locations:
        return "Shoes"
    if locations & {"Right_Accessory", "Left_Accessory", "Both_Accessory"}:
        return "Accessories"
    return None


def client_compatible(info: dict | None) -> tuple[bool, str]:
    if info is None:
        return False, "Missing from active client itemInfo.lua"
    name = str(info.get("identifiedDisplayName") or "").strip()
    resource = str(info.get("identifiedResourceName") or "").strip()
    if name.lower() in INVALID_TEXT:
        return False, "Missing/Unknown identifiedDisplayName in active client itemInfo.lua"
    if resource.lower() in INVALID_TEXT:
        return False, "Missing/Unknown identifiedResourceName in active client itemInfo.lua"
    return True, ""


def build_resource_evidence(iteminfo: dict[int, dict], database: list[dict]) -> dict:
    nonregion_resource_ids: dict[str, list[int]] = defaultdict(list)
    nonregion_class_ids: dict[int, list[int]] = defaultdict(list)
    for item_id, info in iteminfo.items():
        if str(info.get("Server") or "").strip():
            continue
        resource = str(info.get("identifiedResourceName") or "").strip()
        if resource:
            nonregion_resource_ids[resource].append(item_id)
        class_num = info.get("ClassNum")
        if class_num is not None:
            nonregion_class_ids[int(class_num)].append(item_id)

    nonregion_weapon_view_ids: dict[tuple[int, str], list[int]] = defaultdict(list)
    for item in database:
        item_id = int(item["Id"])
        info = iteminfo.get(item_id)
        if info is None or str(info.get("Server") or "").strip():
            continue
        if standard_category(item) != "Weapons":
            continue
        view = int(item.get("View", 0) or 0)
        subtype = str(item.get("SubType", "") or "")
        nonregion_weapon_view_ids[(view, subtype)].append(item_id)

    return {
        "resource": nonregion_resource_ids,
        "class": nonregion_class_ids,
        "weapon_view": nonregion_weapon_view_ids,
    }


def regional_resource_compatible(item: dict, info: dict, category: str, evidence: dict) -> tuple[bool, str, str, str]:
    server_tag = str(info.get("Server") or "").strip()
    if not server_tag:
        return True, "native_untagged", "", ""

    item_id = int(item["Id"])
    resource = str(info.get("identifiedResourceName") or "").strip()
    if item_id in KNOWN_RUNTIME_BAD_IDS or resource in KNOWN_RUNTIME_BAD_RESOURCES:
        return False, f"Known runtime-bad regional resource (Server={server_tag}, Resource={resource})", "", ""

    resource_ids = [x for x in evidence["resource"].get(resource, []) if x != item_id]
    if not resource_ids:
        return False, f"Regional unique identified resource has no non-regional reuse evidence (Server={server_tag}, Resource={resource})", "", ""

    appearance_ids: list[int] = []
    if category == "Headgear":
        class_num = int(info.get("ClassNum") or 0)
        server_view = int(item.get("View", 0) or 0)
        if class_num != server_view:
            return False, f"Regional headgear ClassNum/View mismatch (Server={server_tag}, ClassNum={class_num}, View={server_view})", ",".join(map(str, resource_ids[:8])), ""
        if class_num > 0:
            appearance_ids = [x for x in evidence["class"].get(class_num, []) if x != item_id]
            if not appearance_ids:
                return False, f"Regional headgear appearance ClassNum has no non-regional reuse evidence (Server={server_tag}, ClassNum={class_num})", ",".join(map(str, resource_ids[:8])), ""
    elif category == "Weapons":
        view = int(item.get("View", 0) or 0)
        subtype = str(item.get("SubType", "") or "")
        if view > 0:
            appearance_ids = [x for x in evidence["weapon_view"].get((view, subtype), []) if x != item_id]
            if not appearance_ids:
                return False, f"Regional weapon View/SubType has no non-regional reuse evidence (Server={server_tag}, View={view}, SubType={subtype})", ",".join(map(str, resource_ids[:8])), ""

    return True, "regional_resource_reused", ",".join(map(str, resource_ids[:8])), ",".join(map(str, appearance_ids[:8]))


def has_usable_jobs(item: dict) -> bool:
    jobs = item.get("Jobs")
    return jobs is None or not isinstance(jobs, dict) or any(bool(value) for value in jobs.values())


def level_band(level: int, bands: list[tuple]) -> tuple | None:
    for band in bands:
        _code, _label, minimum, maximum, _price = band
        if level >= minimum and (maximum is None or level <= maximum):
            return band
    return None


def chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def menu_function(func: str, shop_prefix: str, pages: list[list]) -> str:
    if not pages:
        return "\n".join([
            f"function\tscript\t{func}\t{{",
            '\tmes "[Equipment Archive]";',
            '\tmes "No compatible equipment is available in this level band.";',
            "\tnext;",
            "\treturn;",
            "}",
            "",
        ])
    if len(pages) <= MAX_PAGE_OPTIONS:
        labels = [f"Page {number} ({len(page)} items)" for number, page in enumerate(pages, 1)] + ["Back"]
        lines = [f"function\tscript\t{func}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
        for number in range(1, len(pages) + 1):
            lines += [f"\tcase {number}:", "\t\tclose2;", f'\t\tcallshop "{shop_prefix}{number:02d}",1;', "\t\tend;"]
        lines += [f"\tcase {len(pages) + 1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
        return "\n".join(lines)

    groups = chunks(list(enumerate(pages, 1)), MAX_PAGE_OPTIONS)
    output: list[str] = []
    for group_number, group in enumerate(groups, 1):
        group_func = f"{func}G{group_number:02d}"
        labels = [f"Page {number} ({len(page)} items)" for number, page in group] + ["Back"]
        lines = [f"function\tscript\t{group_func}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
        for choice, (page_number, _page) in enumerate(group, 1):
            lines += [f"\tcase {choice}:", "\t\tclose2;", f'\t\tcallshop "{shop_prefix}{page_number:02d}",1;', "\t\tend;"]
        lines += [f"\tcase {len(group) + 1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
        output.append("\n".join(lines))

    group_labels = [f"Pages {group[0][0]}-{group[-1][0]}" for group in groups] + ["Back"]
    lines = [f"function\tscript\t{func}\t{{", '\tswitch(select("' + ':'.join(group_labels) + '")) {']
    for choice, _group in enumerate(groups, 1):
        lines += [f"\tcase {choice}:", f'\t\tcallfunc "{func}G{choice:02d}";', "\t\treturn;"]
    lines += [f"\tcase {len(groups) + 1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    output.append("\n".join(lines))
    return "\n".join(output)


def category_function(func: str, band_rows: list[tuple], counts: dict[str, int]) -> str:
    labels = [f"{label} ({counts.get(code, 0)})" for code, label, *_ in band_rows] + ["Back"]
    lines = [f"function\tscript\t{func}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
    for choice, (code, _label, *_rest) in enumerate(band_rows, 1):
        lines += [f"\tcase {choice}:", f'\t\tcallfunc "{func}{code}";', "\t\treturn;"]
    lines += [f"\tcase {len(band_rows) + 1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    return "\n".join(lines)


def top_category_function(func: str, category_counts: dict[str, int]) -> str:
    labels = [f"{name} ({category_counts.get(name, 0)})" for _code, name in CATEGORIES] + ["Back"]
    lines = [f"function\tscript\t{func}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
    for choice, (code, _name) in enumerate(CATEGORIES, 1):
        lines += [f"\tcase {choice}:", f'\t\tcallfunc "{func}{code}";', "\t\treturn;"]
    lines += [f"\tcase {len(CATEGORIES) + 1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    return "\n".join(lines)


def generate_set(prefix: str, function_prefix: str, bands: list[tuple], selected: list[dict]) -> tuple[str, str, dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    category_counts = Counter()
    band_counts = Counter()
    for row in selected:
        band = level_band(row["EquipLevelMin"], bands)
        if band is None:
            continue
        category_code = next(code for code, name in CATEGORIES if name == row["Category"])
        band_code = band[0]
        row["ShopPrice"] = band[4]
        grouped[(category_code, band_code)].append(row)
        category_counts[row["Category"]] += 1
        band_counts[(category_code, band_code)] += 1

    shop_lines = [
        "//===== rAthena Script =======================================",
        "//= Equipment Archive Hidden Shops",
        "//===== Description: =========================================",
        "//= Active Renewal DB + client ItemInfo with regional resource-reuse safety evidence.",
        "//============================================================",
        "",
    ]
    menu_lines: list[str] = []
    page_counts: dict[str, int] = {}
    for category_code, category_name in CATEGORIES:
        for band_code, _label, *_rest in bands:
            rows = grouped.get((category_code, band_code), [])
            rows.sort(key=lambda row: (row["EquipLevelMin"], row["Name"].casefold(), row["Slots"], row["Id"]))
            pages = chunks(rows, PAGE_SIZE)
            shop_prefix = f"{prefix}{category_code}{band_code}"
            func = f"{function_prefix}{category_code}{band_code}"
            menu_lines.append(menu_function(func, shop_prefix, pages))
            page_counts[f"{category_name}_{band_code}"] = len(pages)
            for page_number, page in enumerate(pages, 1):
                payload = ",".join(f'{row["Id"]}:{row["ShopPrice"]}' for row in page)
                shop_lines.append(f"-\tshop\t{shop_prefix}{page_number:02d}\t-1,{payload}")
        counts = {band_code: band_counts[(category_code, band_code)] for band_code, *_ in bands}
        menu_lines.append(category_function(f"{function_prefix}{category_code}", bands, counts))

    return "\n".join(shop_lines) + "\n", "\n".join(menu_lines), {
        "category_counts": dict(category_counts),
        "band_counts": {f"{category}_{band}": count for (category, band), count in sorted(band_counts.items())},
        "page_counts": page_counts,
        "shop_count": sum(page_counts.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rathena", type=Path, required=True)
    parser.add_argument("--iteminfo", type=Path, required=True)
    args = parser.parse_args()

    root = args.rathena
    item_db_path = root / "db/re/item_db_equip.yml"
    archive = root / "npc/custom/equipment_archive"
    if not item_db_path.is_file():
        parser.error(f"Missing {item_db_path}")
    if not args.iteminfo.is_file():
        parser.error(f"Missing {args.iteminfo}")

    iteminfo, iteminfo_sha = parse_iteminfo(args.iteminfo)
    database = yaml.safe_load(item_db_path.read_text(encoding="utf-8"))["Body"]
    resource_evidence = build_resource_evidence(iteminfo, database)

    included: list[dict] = []
    excluded: list[dict] = []
    warnings: list[dict] = []
    for item in database:
        category = standard_category(item)
        if category is None:
            continue
        item_id = int(item["Id"])
        level_min = int(item.get("EquipLevelMin", 0) or 0)
        level_max = int(item.get("EquipLevelMax", 0) or 0)
        if not has_usable_jobs(item):
            excluded.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Name": item.get("Name", ""), "Category": category, "Reason": "No enabled job can equip this item"})
            continue
        if level_max and level_min > level_max:
            excluded.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Name": item.get("Name", ""), "Category": category, "Reason": "Invalid EquipLevelMin/EquipLevelMax range"})
            continue
        info = iteminfo.get(item_id)
        compatible, reason = client_compatible(info)
        if not compatible:
            excluded.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Name": item.get("Name", ""), "Category": category, "Reason": reason})
            continue

        resource_ok, compatibility_tier, resource_evidence_ids, appearance_evidence_ids = regional_resource_compatible(item, info, category, resource_evidence)
        if not resource_ok:
            excluded.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Name": item.get("Name", ""), "Category": category, "Reason": compatibility_tier})
            continue

        slots = int(item.get("Slots", 0) or 0)
        view = int(item.get("View", 0) or 0)
        client_slots = info.get("slotCount")
        client_class = info.get("ClassNum")
        if client_slots is not None and int(client_slots) != slots:
            warnings.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Warning": f"Server Slots={slots}; client slotCount={client_slots}"})
        if category == "Headgear" and view and client_class is not None and int(client_class) != view:
            warnings.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Warning": f"Server View={view}; client ClassNum={client_class}"})
        if info.get("costume") is True:
            warnings.append({"Id": item_id, "AegisName": item.get("AegisName", ""), "Warning": "Client itemInfo marks costume=true while server uses a standard equipment location"})

        included.append({
            "Id": item_id,
            "AegisName": item.get("AegisName", ""),
            "Name": item.get("Name", ""),
            "ClientName": info.get("identifiedDisplayName") or "",
            "ClientResource": info.get("identifiedResourceName") or "",
            "ClientServerTag": info.get("Server") or "",
            "CompatibilityTier": compatibility_tier,
            "ResourceEvidenceIds": resource_evidence_ids,
            "AppearanceEvidenceIds": appearance_evidence_ids,
            "Category": category,
            "Type": item.get("Type", ""),
            "SubType": item.get("SubType", ""),
            "Locations": ",".join((item.get("Locations") or {}).keys()),
            "EquipLevelMin": level_min,
            "EquipLevelMax": level_max,
            "Slots": slots,
            "ClientSlots": client_slots,
            "View": view,
            "ClientClassNum": client_class,
            "Refineable": bool(item.get("Refineable", False)),
            "Gradable": bool(item.get("Gradable", False)),
        })

    included.sort(key=lambda row: (row["Category"], row["EquipLevelMin"], row["Name"].casefold(), row["Id"]))
    low = [row for row in included if row["EquipLevelMin"] < 100]
    high = [row for row in included if row["EquipLevelMin"] >= 100]
    regional_kept = [row for row in included if str(row.get("ClientServerTag") or "").strip()]
    regional_high_risk_excluded = [row for row in excluded if row["Reason"].startswith("Regional ") or row["Reason"].startswith("Known runtime-bad regional")]

    low_shops, low_menus, low_summary = generate_set("EAL", "F_EAL", LOW_BANDS, low)
    high_shops, high_menus, high_summary = generate_set("EA", "F_EA", HIGH_BANDS, high)

    low_header = "\n".join([
        "//===== rAthena Script =======================================",
        "//= Equipment Archive: Below Lv 100 Menus",
        "//===== Description: =========================================",
        "//= Client-recognized equipment; regional entries require non-regional resource reuse evidence.",
        "//============================================================",
        "",
    ])
    (archive / "equipment_archive_low_level_shops.txt").write_text(low_shops, encoding="utf-8", newline="\n")
    (archive / "equipment_archive_low_level_menu.txt").write_text(low_header + low_menus + top_category_function("F_EAL", low_summary["category_counts"]), encoding="utf-8", newline="\n")
    (archive / "equipment_archive_shops.txt").write_text(high_shops, encoding="utf-8", newline="\n")

    manager = "\n".join([
        "//===== rAthena Script =======================================",
        "//= Equipment Archive Manager",
        "//===== Description: =========================================",
        "//= Standard equipment validated against ItemInfo and regional resource-reuse evidence.",
        "//============================================================",
        "",
        "prontera,153,227,4\tscript\tEquipment Archive#EA\t53,{",
        '\tmes "[Equipment Archive]";',
        '\tmes "Browse every standard weapon, headgear, armor, shield, garment, shoe and accessory that exists in both the active Renewal server database and this server\'s validated client ItemInfo list.";',
        '\tmes "Both slotted and unslotted variants are retained. Regional entries are kept only when their icon and required appearance resources are reused by non-regional client entries.";',
        "\tnext;",
        '\tswitch(select("Below Lv 100 equipment:Lv 100+ Weapons:Lv 100+ Headgear:Lv 100+ Armor:Lv 100+ Shields:Lv 100+ Garments:Lv 100+ Shoes:Lv 100+ Accessories:Price / scope information:Close")) {',
        "\tcase 1: callfunc \"F_EAL\"; close;",
        "\tcase 2: callfunc \"F_EAW\"; close;",
        "\tcase 3: callfunc \"F_EAH\"; close;",
        "\tcase 4: callfunc \"F_EAA\"; close;",
        "\tcase 5: callfunc \"F_EAS\"; close;",
        "\tcase 6: callfunc \"F_EAG\"; close;",
        "\tcase 7: callfunc \"F_EAF\"; close;",
        "\tcase 8: callfunc \"F_EAX\"; close;",
        "\tcase 9:",
        '\t\tmes "[Equipment Archive]";',
        '\t\tmes "Below Lv 100: 100,000 Zeny";',
        '\t\tmes "Lv 100-129: 200,000 Zeny";',
        '\t\tmes "Lv 130-159: 500,000 Zeny";',
        '\t\tmes "Lv 160-199: 1,000,000 Zeny";',
        '\t\tmes "Lv 200+: 2,000,000 Zeny";',
        '\t\tmes "Included: standard equipment recognized by ItemInfo; regional entries additionally require non-regional icon and appearance reuse evidence.";',
        '\t\tmes "Excluded: costumes, shadow gear, pet equipment, missing/Unknown ItemInfo records, unique regional resources without reuse evidence, and known runtime-bad resources.";',
        "\t\tclose;",
        "\tdefault: close;",
        "\t}",
        "\tclose;",
        "}",
        "",
        high_menus,
    ])
    (archive / "equipment_archive_manager.txt").write_text(manager, encoding="utf-8", newline="\n")

    audit_dir = archive / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    fields = list(included[0].keys())
    with (audit_dir / "equipment_archive_included_full.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(included)
    with (audit_dir / "equipment_archive_excluded_client_incompatible.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Id", "AegisName", "Name", "Category", "Reason"])
        writer.writeheader()
        writer.writerows(excluded)
    with (audit_dir / "equipment_archive_client_server_warnings.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Id", "AegisName", "Warning"])
        writer.writeheader()
        writer.writerows(warnings)
    with (audit_dir / "equipment_archive_regional_resources_kept.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(regional_kept)
    with (audit_dir / "equipment_archive_regional_high_risk_excluded.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Id", "AegisName", "Name", "Category", "Reason"])
        writer.writeheader()
        writer.writerows(regional_high_risk_excluded)

    summary = {
        "iteminfo_path_name": args.iteminfo.name,
        "iteminfo_sha256": iteminfo_sha,
        "iteminfo_id_count": len(iteminfo),
        "renewal_item_db_equipment_rows": len(database),
        "included_standard_equipment": len(included),
        "included_low_level": len(low),
        "included_high_level": len(high),
        "excluded_standard_equipment": len(excluded),
        "warning_count": len(warnings),
        "regional_resource_reused_kept": len(regional_kept),
        "regional_high_risk_excluded": len(regional_high_risk_excluded),
        "regional_kept_tags": dict(Counter(row["ClientServerTag"] for row in regional_kept)),
        "known_runtime_bad_ids_excluded": sorted(KNOWN_RUNTIME_BAD_IDS),
        "clown_smiling_410345_included": any(row["Id"] == 410345 for row in included),
        "clown_smiling_410345_client_name": iteminfo.get(410345, {}).get("identifiedDisplayName"),
        "low": low_summary,
        "high": high_summary,
    }
    (audit_dir / "equipment_archive_full_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
