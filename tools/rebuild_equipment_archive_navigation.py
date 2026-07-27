#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "npc/custom/equipment_archive"
AUDIT_CSV = ARCHIVE / "audit/equipment_archive_included_full.csv"
MANAGER = ARCHIVE / "equipment_archive_manager.txt"
SHOPS = ARCHIVE / "equipment_archive_shops.txt"
LOW_MENU = ARCHIVE / "equipment_archive_low_level_menu.txt"
LOW_SHOPS = ARCHIVE / "equipment_archive_low_level_shops.txt"
NAV_AUDIT = ARCHIVE / "audit/equipment_archive_navigation_audit.csv"
NAV_SUMMARY = ARCHIVE / "audit/equipment_archive_navigation_summary.json"

PAGE_SIZE = 40
PAGE_MENU_SIZE = 8

BANDS = [
    ("L0", "Lv 0-99", 0, 99),
    ("L1", "Lv 100-129", 100, 129),
    ("L2", "Lv 130-159", 130, 159),
    ("L3", "Lv 160-199", 160, 199),
    ("L4", "Lv 200+", 200, 9999),
]

WEAPON_FAMILIES = OrderedDict([
    ("Blades", ["Dagger", "1hSword", "2hSword", "Katar"]),
    ("Heavy weapons", ["1hAxe", "2hAxe", "Mace", "Knuckle"]),
    ("Polearms", ["1hSpear", "2hSpear"]),
    ("Magic weapons", ["Staff", "2hStaff", "Book"]),
    ("Ranged weapons", ["Bow", "Revolver", "Rifle", "Gatling", "Shotgun", "Grenade"]),
    ("Performer / Ninja", ["Musical", "Whip", "Huuma"]),
])

SUBTYPE_LABELS = {
    "Dagger": "Daggers",
    "1hSword": "One-handed swords",
    "2hSword": "Two-handed swords",
    "Katar": "Katars",
    "1hAxe": "One-handed axes",
    "2hAxe": "Two-handed axes",
    "Mace": "Maces",
    "Knuckle": "Knuckles",
    "1hSpear": "One-handed spears",
    "2hSpear": "Two-handed spears",
    "Staff": "One-handed staves",
    "2hStaff": "Two-handed staves",
    "Book": "Books",
    "Bow": "Bows",
    "Revolver": "Revolvers",
    "Rifle": "Rifles",
    "Gatling": "Gatling guns",
    "Shotgun": "Shotguns",
    "Grenade": "Grenade launchers",
    "Musical": "Instruments",
    "Whip": "Whips",
    "Huuma": "Huuma shuriken",
}

HEAD_SLOT_ORDER = [
    "Top only",
    "Middle only",
    "Lower only",
    "Top + Middle",
    "Middle + Lower",
    "Other multi-slot",
]

ACCESSORY_SLOT_ORDER = ["Either accessory slot", "Left accessory only", "Right accessory only"]
OTHER_CATEGORY_ORDER = ["Armor", "Shields", "Garments", "Shoes"]


def clean_display(value: str) -> str:
    value = (value or "").strip()
    return re.sub(r"\s+", " ", value)


def sort_key(value: str):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return (value.casefold(), value)


def band_for(level: int):
    for code, label, low, high in BANDS:
        if low <= level <= high:
            return code, label
    return "L4", "Lv 200+"


def head_slot(locations: str) -> str:
    parts = {p.strip() for p in (locations or "").split(",") if p.strip()}
    if parts == {"Head_Top"}:
        return "Top only"
    if parts == {"Head_Mid"}:
        return "Middle only"
    if parts == {"Head_Low"}:
        return "Lower only"
    if parts == {"Head_Top", "Head_Mid"}:
        return "Top + Middle"
    if parts == {"Head_Mid", "Head_Low"}:
        return "Middle + Lower"
    return "Other multi-slot"


def accessory_slot(locations: str) -> str:
    return {
        "Both_Accessory": "Either accessory slot",
        "Left_Accessory": "Left accessory only",
        "Right_Accessory": "Right accessory only",
    }.get(locations, "Either accessory slot")


def script_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def menu_text(value: str, max_len: int = 25) -> str:
    value = clean_display(value).replace(":", "-")
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def choose_menu(lines: list[str], calls: list[str], back_label: str = "Back") -> list[str]:
    assert len(lines) == len(calls)
    options = lines + [back_label]
    out = [f'\tswitch(select("{script_string(":".join(options))}")) {{']
    for idx, call in enumerate(calls, 1):
        out.extend([f"\tcase {idx}:", *["\t\t" + x for x in call.split("\n")]])
    out.extend([f"\tcase {len(options)}:", "\t\treturn;", "\t}", "\treturn;"])
    return out


def choose_menu_loop(lines: list[str], calls: list[str], back_label: str = "Back") -> list[str]:
    assert len(lines) == len(calls)
    options = lines + [back_label]
    out = ["\twhile (1) {", f'\t\tswitch(select("{script_string(":".join(options))}")) {{']
    for idx, call in enumerate(calls, 1):
        out.extend([f"\t\tcase {idx}:", *["\t\t\t" + x for x in call.split("\n")], "\t\t\tbreak;"])
    out.extend([f"\t\tcase {len(options)}:", "\t\t\treturn;", "\t\t}", "\t}", "\treturn;"])
    return out


@dataclass
class Item:
    item_id: int
    aegis: str
    name: str
    display: str
    category: str
    subtype: str
    locations: str
    level: int
    price: int
    band_code: str
    band_label: str
    leaf_path: tuple[str, ...]


@dataclass
class Page:
    index: int
    shop: str
    items: list[Item]
    path_parts: tuple[str, ...]
    page_number: int
    page_count: int

    @property
    def first_name(self):
        return self.items[0].display

    @property
    def last_name(self):
        return self.items[-1].display

    @property
    def short_range(self):
        return f"{menu_text(self.first_name, 8)} - {menu_text(self.last_name, 8)}"

    @property
    def full_path(self):
        return " > ".join((*self.path_parts, f"Page {self.page_number}: {self.first_name} - {self.last_name}"))


def read_items() -> list[Item]:
    rows = []
    with AUDIT_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            category = row["Category"]
            subtype = row.get("SubType", "") or ""
            locations = row.get("Locations", "") or ""
            level = int(row.get("EquipLevelMin") or 0)
            band_code, band_label = band_for(level)
            display = clean_display(row.get("ClientName") or row.get("Name") or row.get("AegisName"))
            if category == "Weapons":
                leaf = ("Weapons", SUBTYPE_LABELS.get(subtype, subtype or "Other weapons"), band_label)
            elif category == "Headgear":
                leaf = ("Headgear", head_slot(locations), band_label)
            elif category == "Accessories":
                leaf = ("Accessories", accessory_slot(locations), band_label)
            else:
                leaf = (category, band_label)
            rows.append(Item(
                item_id=int(row["Id"]),
                aegis=row["AegisName"],
                name=row["Name"],
                display=display,
                category=category,
                subtype=subtype,
                locations=locations,
                level=level,
                price=int(row["ShopPrice"]),
                band_code=band_code,
                band_label=band_label,
                leaf_path=leaf,
            ))
    ids = [x.item_id for x in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate item IDs in included audit")
    return rows


def build_pages(items: list[Item]):
    leaves: OrderedDict[tuple[str, ...], list[Item]] = OrderedDict()

    # Build in deliberate navigation order.
    for _, subtypes in WEAPON_FAMILIES.items():
        for subtype in subtypes:
            label = SUBTYPE_LABELS[subtype]
            for _, band_label, _, _ in BANDS:
                leaf = ("Weapons", label, band_label)
                selected = [x for x in items if x.leaf_path == leaf]
                if selected:
                    leaves[leaf] = selected

    for slot in HEAD_SLOT_ORDER:
        for _, band_label, _, _ in BANDS:
            leaf = ("Headgear", slot, band_label)
            selected = [x for x in items if x.leaf_path == leaf]
            if selected:
                leaves[leaf] = selected

    for category in OTHER_CATEGORY_ORDER:
        for _, band_label, _, _ in BANDS:
            leaf = (category, band_label)
            selected = [x for x in items if x.leaf_path == leaf]
            if selected:
                leaves[leaf] = selected

    for slot in ACCESSORY_SLOT_ORDER:
        for _, band_label, _, _ in BANDS:
            leaf = ("Accessories", slot, band_label)
            selected = [x for x in items if x.leaf_path == leaf]
            if selected:
                leaves[leaf] = selected

    assigned = {x.item_id for values in leaves.values() for x in values}
    missing = [x for x in items if x.item_id not in assigned]
    if missing:
        raise RuntimeError(f"Unassigned items: {[(x.item_id, x.leaf_path) for x in missing[:20]]}")

    pages: list[Page] = []
    leaf_pages: OrderedDict[tuple[str, ...], list[Page]] = OrderedDict()
    for leaf, selected in leaves.items():
        selected = sorted(selected, key=lambda x: (sort_key(x.display), x.item_id))
        chunks = [selected[i:i + PAGE_SIZE] for i in range(0, len(selected), PAGE_SIZE)]
        leaf_pages[leaf] = []
        for page_no, chunk in enumerate(chunks, 1):
            index = len(pages)
            page = Page(index=index, shop=f"EA{index + 1:04d}", items=chunk, path_parts=leaf,
                        page_number=page_no, page_count=len(chunks))
            pages.append(page)
            leaf_pages[leaf].append(page)
    return leaves, pages, leaf_pages


def generate_shops(pages: list[Page]):
    out = [
        "//===== rAthena Script =======================================",
        "//= Equipment Archive Hidden Shops - Navigation Redesign",
        "//===== Description: =========================================",
        "//= Exact same validated 5,885-item safety set, reorganized by",
        "//= equipment type, detailed subtype/slot, level and name.",
        "//============================================================",
        "",
    ]
    for page in pages:
        inventory = ",".join(f"{x.item_id}:{x.price}" for x in page.items)
        out.append(f"-\tshop\t{page.shop}\t-1,{inventory}")
    SHOPS.write_text("\n".join(out) + "\n", encoding="utf-8")
    LOW_SHOPS.write_text(
        "// Equipment Archive low-level shops are now integrated into equipment_archive_shops.txt.\n"
        "// This compatibility stub intentionally defines no shops.\n",
        encoding="utf-8",
    )
    LOW_MENU.write_text(
        "// Equipment Archive low-level navigation is now integrated into equipment_archive_manager.txt.\n"
        "// This compatibility stub intentionally defines no functions.\n",
        encoding="utf-8",
    )


def leaf_function_name(leaf_index: int) -> str:
    return f"F_EAL{leaf_index:03d}"


def generate_leaf_functions(leaf_pages: OrderedDict[tuple[str, ...], list[Page]]):
    out = []
    leaf_function = {}
    for leaf_index, (leaf, pages) in enumerate(leaf_pages.items(), 1):
        base = leaf_function_name(leaf_index)
        leaf_function[leaf] = base
        if len(pages) <= PAGE_MENU_SIZE:
            out.extend([f"function\tscript\t{base}\t{{"])
            labels = [f"P{p.page_number:02d} {p.short_range} ({len(p.items)})" for p in pages]
            calls = [f'close2;\ncallshop "{p.shop}",1;\nend;' for p in pages]
            out.extend(choose_menu(labels, calls))
            out.extend(["}", ""])
            continue

        range_functions = []
        range_labels = []
        for range_index, start in enumerate(range(0, len(pages), PAGE_MENU_SIZE), 1):
            chunk = pages[start:start + PAGE_MENU_SIZE]
            rfn = f"{base}R{range_index}"
            range_functions.append(rfn)
            range_labels.append(
                f"Pages {chunk[0].page_number}-{chunk[-1].page_number}: "
                f"{menu_text(chunk[0].first_name, 8)} - {menu_text(chunk[-1].last_name, 8)}"
            )
            out.extend([f"function\tscript\t{rfn}\t{{"])
            labels = [f"P{p.page_number:02d} {p.short_range} ({len(p.items)})" for p in chunk]
            calls = [f'close2;\ncallshop "{p.shop}",1;\nend;' for p in chunk]
            out.extend(choose_menu(labels, calls))
            out.extend(["}", ""])

        out.extend([f"function\tscript\t{base}\t{{"])
        calls = [f'callfunc "{fn}";' for fn in range_functions]
        out.extend(choose_menu_loop(range_labels, calls))
        out.extend(["}", ""])
    return out, leaf_function


def generate_navigation_functions(items: list[Item], leaves, leaf_function):
    out = []

    # Weapons: family -> subtype -> level.
    subtype_function = {}
    for family_index, (family, subtypes) in enumerate(WEAPON_FAMILIES.items(), 1):
        family_fn = f"F_EAWF{family_index}"
        labels, calls = [], []
        for subtype_index, subtype in enumerate(subtypes, 1):
            label = SUBTYPE_LABELS[subtype]
            matching_leaves = [leaf for leaf in leaves if len(leaf) == 3 and leaf[0] == "Weapons" and leaf[1] == label]
            if not matching_leaves:
                continue
            fn = f"F_EAWS{family_index}{subtype_index}"
            subtype_function[(family, subtype)] = fn
            count = sum(len(leaves[leaf]) for leaf in matching_leaves)
            labels.append(f"{label} ({count})")
            calls.append(f'callfunc "{fn}";')

            out.extend([f"function\tscript\t{fn}\t{{"])
            band_labels, band_calls = [], []
            for _, band_label, _, _ in BANDS:
                leaf = ("Weapons", label, band_label)
                if leaf not in leaves:
                    continue
                band_labels.append(f"{band_label} ({len(leaves[leaf])})")
                band_calls.append(f'callfunc "{leaf_function[leaf]}";')
            out.extend(choose_menu_loop(band_labels, band_calls))
            out.extend(["}", ""])

        out.extend([f"function\tscript\t{family_fn}\t{{"])
        out.extend(choose_menu_loop(labels, calls))
        out.extend(["}", ""])

    out.extend(["function\tscript\tF_EA_WEAPONS\t{"])
    labels, calls = [], []
    for family_index, (family, subtypes) in enumerate(WEAPON_FAMILIES.items(), 1):
        count = sum(1 for x in items if x.category == "Weapons" and x.subtype in subtypes)
        if count:
            labels.append(f"{family} ({count})")
            calls.append(f'callfunc "F_EAWF{family_index}";')
    out.extend(choose_menu_loop(labels, calls))
    out.extend(["}", ""])

    # Headgear: slot -> level.
    slot_calls = []
    slot_labels = []
    for idx, slot in enumerate(HEAD_SLOT_ORDER, 1):
        matching = [leaf for leaf in leaves if len(leaf) == 3 and leaf[0] == "Headgear" and leaf[1] == slot]
        if not matching:
            continue
        fn = f"F_EAHS{idx}"
        count = sum(len(leaves[leaf]) for leaf in matching)
        slot_labels.append(f"{slot} ({count})")
        slot_calls.append(f'callfunc "{fn}";')
        out.extend([f"function\tscript\t{fn}\t{{"])
        labels, calls = [], []
        for _, band_label, _, _ in BANDS:
            leaf = ("Headgear", slot, band_label)
            if leaf in leaves:
                labels.append(f"{band_label} ({len(leaves[leaf])})")
                calls.append(f'callfunc "{leaf_function[leaf]}";')
        out.extend(choose_menu_loop(labels, calls))
        out.extend(["}", ""])
    out.extend(["function\tscript\tF_EA_HEADGEAR\t{"])
    out.extend(choose_menu_loop(slot_labels, slot_calls))
    out.extend(["}", ""])

    # Other simple categories: level directly.
    for category in OTHER_CATEGORY_ORDER:
        fn = f"F_EA_{category.upper()}"
        out.extend([f"function\tscript\t{fn}\t{{"])
        labels, calls = [], []
        for _, band_label, _, _ in BANDS:
            leaf = (category, band_label)
            if leaf in leaves:
                labels.append(f"{band_label} ({len(leaves[leaf])})")
                calls.append(f'callfunc "{leaf_function[leaf]}";')
        out.extend(choose_menu_loop(labels, calls))
        out.extend(["}", ""])

    # Accessories: slot -> level.
    slot_labels, slot_calls = [], []
    for idx, slot in enumerate(ACCESSORY_SLOT_ORDER, 1):
        matching = [leaf for leaf in leaves if len(leaf) == 3 and leaf[0] == "Accessories" and leaf[1] == slot]
        if not matching:
            continue
        fn = f"F_EAXS{idx}"
        count = sum(len(leaves[leaf]) for leaf in matching)
        slot_labels.append(f"{slot} ({count})")
        slot_calls.append(f'callfunc "{fn}";')
        out.extend([f"function\tscript\t{fn}\t{{"])
        labels, calls = [], []
        for _, band_label, _, _ in BANDS:
            leaf = ("Accessories", slot, band_label)
            if leaf in leaves:
                labels.append(f"{band_label} ({len(leaves[leaf])})")
                calls.append(f'callfunc "{leaf_function[leaf]}";')
        out.extend(choose_menu_loop(labels, calls))
        out.extend(["}", ""])
    out.extend(["function\tscript\tF_EA_ACCESSORIES\t{"])
    out.extend(choose_menu_loop(slot_labels, slot_calls))
    out.extend(["}", ""])
    return out


def setarray_lines(array_name: str, values: list, quote: bool, chunk_size: int = 80):
    out = []
    for start in range(0, len(values), chunk_size):
        chunk = values[start:start + chunk_size]
        rendered = []
        for value in chunk:
            if quote:
                rendered.append(f'"{script_string(str(value))}"')
            else:
                rendered.append(str(value))
        out.append(f"\tsetarray {array_name}[{start}],")
        # Keep generated source readable and parser-safe.
        for sub_start in range(0, len(rendered), 10):
            sub = rendered[sub_start:sub_start + 10]
            suffix = "," if sub_start + 10 < len(rendered) else ";"
            out.append("\t\t" + ",".join(sub) + suffix)
    return out


def generate_manager(items: list[Item], pages: list[Page], leaf_functions, nav_functions):
    page_by_item = {x.item_id: page.index for page in pages for x in page.items}
    sorted_items = sorted(items, key=lambda x: x.item_id)

    out = [
        "//===== rAthena Script =======================================",
        "//= Equipment Archive Manager - Searchable Navigation Edition",
        "//===== Description: =========================================",
        "//= Preserves the exact validated safety set while reorganizing",
        "//= by equipment type, detailed subtype/slot, level and name.",
        "//= Includes direct Item ID lookup to open the exact shop page.",
        "//============================================================",
        "",
        "prontera,153,227,4\tscript\tEquipment Archive#EA\t53,{",
        "\twhile (1) {",
        "\t\tclear;",
        "\t\tmes \"[Equipment Archive]\";",
        "\t\tmes \"Find equipment by a clear category path, or enter an Item ID to open its exact alphabetical page.\";",
        "\t\tnext;",
        "\t\tswitch(select(\"Find by Item ID:Weapons:Headgear:Armor:Shields:Garments:Shoes:Accessories:Price / safety information:Close\")) {",
        "\t\tcase 1: callfunc \"F_EA_SEARCH\"; break;",
        "\t\tcase 2: callfunc \"F_EA_WEAPONS\"; break;",
        "\t\tcase 3: callfunc \"F_EA_HEADGEAR\"; break;",
        "\t\tcase 4: callfunc \"F_EA_ARMOR\"; break;",
        "\t\tcase 5: callfunc \"F_EA_SHIELDS\"; break;",
        "\t\tcase 6: callfunc \"F_EA_GARMENTS\"; break;",
        "\t\tcase 7: callfunc \"F_EA_SHOES\"; break;",
        "\t\tcase 8: callfunc \"F_EA_ACCESSORIES\"; break;",
        "\t\tcase 9:",
        "\t\t\tmes \"[Equipment Archive]\";",
        "\t\t\tmes \"Prices are based on minimum required Base Level:\";",
        "\t\t\tmes \"Lv 0-99: 100,000 Zeny\";",
        "\t\t\tmes \"Lv 100-129: 200,000 Zeny\";",
        "\t\t\tmes \"Lv 130-159: 500,000 Zeny\";",
        "\t\t\tmes \"Lv 160-199: 1,000,000 Zeny\";",
        "\t\t\tmes \"Lv 200+: 2,000,000 Zeny\";",
        "\t\t\tnext;",
        "\t\t\tmes \"[Equipment Archive]\";",
        "\t\t\tmes \"The archive still contains exactly 5,885 standard equipment entries from the previously validated client-safe set.\";",
        "\t\t\tmes \"No removed regional or known runtime-bad resource was restored by this navigation redesign.\";",
        "\t\t\tnext;",
        "\t\t\tbreak;",
        "\t\tdefault: close;",
        "\t\t}",
        "\t}",
        "\tend;",
        "",
        "OnInit:",
        f"\t$@EA_ItemCount = {len(sorted_items)};",
        f"\t$@EA_PageCount = {len(pages)};",
    ]
    out += setarray_lines("$@EA_PageShop$", [p.shop for p in pages], True, 50)
    out += setarray_lines("$@EA_PagePath$", [p.full_path for p in pages], True, 30)
    out += setarray_lines("$@EA_ItemId", [x.item_id for x in sorted_items], False, 100)
    out += setarray_lines("$@EA_ItemPage", [page_by_item[x.item_id] for x in sorted_items], False, 100)
    out += ["\tend;", "}", ""]

    out += [
        "function\tscript\tF_EA_SEARCH\t{",
        "\tmes \"[Equipment Archive Search]\";",
        "\tmes \"Enter the numeric Item ID.\";",
        "\tmes \"This lookup only searches the validated Equipment Archive inventory.\";",
        "\tinput .@item_id;",
        "\tif (.@item_id <= 0 || getiteminfo(.@item_id, ITEMINFO_ID) != .@item_id) {",
        "\t\tmes \"[Equipment Archive Search]\";",
        "\t\tmes \"That is not a valid server Item ID.\";",
        "\t\treturn;",
        "\t}",
        "\t.@low = 0;",
        "\t.@high = $@EA_ItemCount - 1;",
        "\t.@found = -1;",
        "\twhile (.@low <= .@high) {",
        "\t\t.@mid = (.@low + .@high) / 2;",
        "\t\tif ($@EA_ItemId[.@mid] == .@item_id) {",
        "\t\t\t.@found = .@mid;",
        "\t\t\tbreak;",
        "\t\t}",
        "\t\tif ($@EA_ItemId[.@mid] < .@item_id)",
        "\t\t\t.@low = .@mid + 1;",
        "\t\telse",
        "\t\t\t.@high = .@mid - 1;",
        "\t}",
        "\tmes \"[Equipment Archive Search]\";",
        "\tif (.@found < 0) {",
        "\t\tmes mesitemlink(.@item_id) + \" is not sold by this archive.\";",
        "\t\tmes \"It may be a costume, shadow item, pet item, client-incompatible entry, or otherwise outside the validated standard-equipment set.\";",
        "\t\treturn;",
        "\t}",
        "\t.@page = $@EA_ItemPage[.@found];",
        "\tmes mesitemlink(.@item_id);",
        "\tmes \"Location: ^0000FF\" + $@EA_PagePath$[.@page] + \"^000000\";",
        "\tnext;",
        "\tif (select(\"Open exact shop page:Back\") == 1) {",
        "\t\tclose2;",
        "\t\tcallshop($@EA_PageShop$[.@page],1);",
        "\t\tend;",
        "\t}",
        "\treturn;",
        "}",
        "",
    ]
    out += nav_functions
    out += leaf_functions
    MANAGER.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_audits(items: list[Item], pages: list[Page]):
    rows = []
    for page in pages:
        for order, item in enumerate(page.items, 1):
            rows.append({
                "ItemID": item.item_id,
                "AegisName": item.aegis,
                "Name": item.name,
                "DisplayName": item.display,
                "Category": item.category,
                "SubType": item.subtype,
                "Locations": item.locations,
                "EquipLevelMin": item.level,
                "Price": item.price,
                "NavigationPath": " > ".join(page.path_parts),
                "Shop": page.shop,
                "Page": page.page_number,
                "PageCount": page.page_count,
                "OrderOnPage": order,
            })
    with NAV_AUDIT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    category_counts = {}
    for item in items:
        category_counts[item.category] = category_counts.get(item.category, 0) + 1
    summary = {
        "validated_item_count": len(items),
        "shop_page_count": len(pages),
        "page_size": PAGE_SIZE,
        "duplicate_item_ids": len(items) - len({x.item_id for x in items}),
        "category_counts": category_counts,
        "navigation": {
            "weapons": "family > exact weapon subtype > required-level band > alphabetical page",
            "headgear": "head slot > required-level band > alphabetical page",
            "armor_shields_garments_shoes": "required-level band > alphabetical page",
            "accessories": "equip side > required-level band > alphabetical page",
            "direct_lookup": "binary Item ID lookup opens exact page",
        },
    }
    NAV_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate(items: list[Item], pages: list[Page]):
    page_items = [x.item_id for p in pages for x in p.items]
    source_items = [x.item_id for x in items]
    assert len(page_items) == 5885, len(page_items)
    assert len(page_items) == len(set(page_items)), "duplicate shop items"
    assert set(page_items) == set(source_items), "shop/audit item mismatch"
    assert all(1 <= len(p.items) <= PAGE_SIZE for p in pages)
    assert all(p.items == sorted(p.items, key=lambda x: (sort_key(x.display), x.item_id)) for p in pages)
    manager = MANAGER.read_text(encoding="utf-8")
    shops = SHOPS.read_text(encoding="utf-8")
    assert manager.count("function\tscript") > 50
    assert shops.count("\n-\tshop\t") == len(pages)


def main():
    items = read_items()
    leaves, pages, leaf_pages = build_pages(items)
    generate_shops(pages)
    leaf_functions, leaf_function_map = generate_leaf_functions(leaf_pages)
    nav_functions = generate_navigation_functions(items, leaves, leaf_function_map)
    generate_manager(items, pages, leaf_functions, nav_functions)
    write_audits(items, pages)
    validate(items, pages)
    print(f"Generated {len(pages)} alphabetical shops for {len(items)} validated items.")


if __name__ == "__main__":
    main()
