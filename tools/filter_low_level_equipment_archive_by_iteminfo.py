#!/usr/bin/env python3
"""Filter Equipment Archive's Below-Lv-100 shops against actual client itemInfo.lua."""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

SHOP_RE = re.compile(r"^-\tshop\t(EAL([WHASGFX])([ABCD])(\d{2}))\t-1,(.+)$")
ITEM_RE = re.compile(r"(\d+):(\d+)")
ID_PATTERNS = [re.compile(rb"\[\s*(\d+)\s*\]\s*="), re.compile(rb"\bITEMID\s*\[\s*(\d+)\s*\]")]
CATEGORIES = [("W","Weapons"),("H","Headgear"),("A","Armor"),("S","Shields"),("G","Garments"),("F","Shoes"),("X","Accessories")]
BANDS = [("A","Req. Lv 0-29"),("B","Req. Lv 30-59"),("C","Req. Lv 60-79"),("D","Req. Lv 80-99")]


def parse_client_ids(path: Path) -> set[int]:
    data = path.read_bytes()
    ids: set[int] = set()
    for pattern in ID_PATTERNS:
        ids.update(int(m.group(1)) for m in pattern.finditer(data))
    if len(ids) < 1000:
        raise ValueError(f"Only {len(ids)} Item IDs detected. Use the large SystemEN/LuaFiles514/itemInfo.lua, not the small loader.")
    return ids


def parse_shops(path: Path):
    grouped = defaultdict(list)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = SHOP_RE.match(line)
        if not m:
            continue
        shop, category, band, _page, payload = m.groups()
        for pair in payload.split(','):
            im = ITEM_RE.fullmatch(pair.strip())
            if not im:
                raise ValueError(f"Invalid shop item pair in {shop}: {pair!r}")
            grouped[(category,band)].append((int(im.group(1)), int(im.group(2)), shop))
    if not grouped:
        raise ValueError(f"No EAL low-level shops found in {path}")
    return grouped


def page_function(category: str, band: str, pages) -> str:
    func = f"F_EAL{category}{band}"
    if not pages:
        return "\n".join([
            f"function\tscript\t{func}\t{{",
            '\tmes "[Equipment Archive]";',
            '\tmes "No client-compatible items remain in this level band.";',
            "\tnext;", "\treturn;", "}", ""
        ])
    labels = [f"Page {i+1} ({len(page)} items)" for i,page in enumerate(pages)] + ["Back"]
    out = [f"function\tscript\t{func}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
    for i in range(1, len(pages)+1):
        out += [f"\tcase {i}:", "\t\tclose2;", f'\t\tcallshop "EAL{category}{band}{i:02d}",1;', "\t\tend;"]
    out += [f"\tcase {len(pages)+1}:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    return "\n".join(out)


def category_function(category: str, totals) -> str:
    labels = [f"{label} ({totals.get(code,0)})" for code,label in BANDS] + ["Back"]
    out = [f"function\tscript\tF_EAL{category}\t{{", '\tswitch(select("' + ':'.join(labels) + '")) {']
    for i,(code,_label) in enumerate(BANDS,1):
        out += [f"\tcase {i}:", f'\t\tcallfunc "F_EAL{category}{code}";', "\t\treturn;"]
    out += ["\tcase 5:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    return "\n".join(out)


def build_menu(category_totals, band_totals, pages_by_key) -> str:
    out = [
        "//===== rAthena Script =======================================",
        "//= Equipment Archive: Below Lv 100 Menus",
        "//===== Description: =========================================",
        "//= Exact intersection with the active client itemInfo.lua.",
        "//============================================================", ""
    ]
    for category,_name in CATEGORIES:
        for band,_label in BANDS:
            out.append(page_function(category, band, pages_by_key.get((category,band), [])))
        out.append(category_function(category, {b:band_totals.get((category,b),0) for b,_ in BANDS}))
    labels = [f"{name} ({category_totals.get(code,0)})" for code,name in CATEGORIES] + ["Back"]
    out += ["function\tscript\tF_EAL\t{", '\tswitch(select("' + ':'.join(labels) + '")) {']
    for i,(code,_name) in enumerate(CATEGORIES,1):
        out += [f"\tcase {i}:", f'\t\tcallfunc "F_EAL{code}";', "\t\treturn;"]
    out += ["\tcase 8:", "\t\treturn;", "\t}", "\treturn;", "}", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rathena", required=True, type=Path)
    ap.add_argument("--iteminfo", required=True, type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    ea = args.rathena / "npc/custom/equipment_archive"
    shops = ea / "equipment_archive_low_level_shops.txt"
    menu = ea / "equipment_archive_low_level_menu.txt"
    if not shops.is_file() or not menu.is_file():
        ap.error(f"Equipment Archive files not found below {ea}")
    if not args.iteminfo.is_file():
        ap.error(f"itemInfo.lua not found: {args.iteminfo}")

    client_ids = parse_client_ids(args.iteminfo)
    grouped = parse_shops(shops)
    kept_by_key = {}
    removed = []
    before = 0
    for key, entries in grouped.items():
        before += len(entries)
        kept = []
        for item_id, price, source_shop in entries:
            if item_id in client_ids:
                kept.append((item_id,price,source_shop))
            else:
                removed.append((item_id,price,key[0],key[1],source_shop,"Missing from active client itemInfo.lua"))
        kept_by_key[key] = kept
    pages_by_key = {key:[items[i:i+40] for i in range(0,len(items),40)] for key,items in kept_by_key.items()}
    after = sum(len(v) for v in kept_by_key.values())
    print(f"Client itemInfo IDs: {len(client_ids)}")
    print(f"Low-level archive: {before} -> {after}; removed {len(removed)}")
    print(f"Clown_Smiling_ [410345] in client itemInfo: {'YES' if 410345 in client_ids else 'NO'}")
    if args.check:
        return 0

    for path in (shops, menu):
        backup = path.with_suffix(path.suffix + ".before_iteminfo_filter")
        if not backup.exists():
            shutil.copy2(path, backup)

    shop_lines = [
        "//===== rAthena Script =======================================",
        "//= Equipment Archive: Below Lv 100 Hidden Shops",
        "//===== Description: =========================================",
        "//= Exact intersection with the active client itemInfo.lua.",
        "//============================================================", ""
    ]
    for category,_name in CATEGORIES:
        for band,_label in BANDS:
            for page_no,page in enumerate(pages_by_key.get((category,band),[]),1):
                payload = ','.join(f"{item_id}:{price}" for item_id,price,_source in page)
                shop_lines.append(f"-\tshop\tEAL{category}{band}{page_no:02d}\t-1,{payload}")
    shops.write_text("\n".join(shop_lines)+"\n", encoding="utf-8", newline="\n")

    category_totals = {c:sum(len(kept_by_key.get((c,b),[])) for b,_ in BANDS) for c,_ in CATEGORIES}
    band_totals = {(c,b):len(kept_by_key.get((c,b),[])) for c,_ in CATEGORIES for b,_ in BANDS}
    menu.write_text(build_menu(category_totals,band_totals,pages_by_key), encoding="utf-8", newline="\n")

    audit = ea / "audit/client_iteminfo_removed_low_level_items.csv"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Item ID","Shop Price","Category Code","Level Band","Original Shop","Removal Reason"])
        w.writerows(sorted(removed))
    print(f"Updated: {shops}")
    print(f"Updated: {menu}")
    print(f"Audit: {audit}")
    print("Run @reloadscript after copying the generated files to the server.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
