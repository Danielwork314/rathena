#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'npc/custom/equipment_archive'
BUYER_DIR = ROOT / 'npc/custom/high_level_equipment_buyer'

source_csv = ARCHIVE / 'audit/equipment_archive_included_full.csv'
nav_csv = ARCHIVE / 'audit/equipment_archive_navigation_audit.csv'
manager = ARCHIVE / 'equipment_archive_manager.txt'
shops = ARCHIVE / 'equipment_archive_shops.txt'
buyer = BUYER_DIR / 'high_level_equipment_buyer.txt'
material_audit = BUYER_DIR / 'high_level_equipment_buyer_material_special_prices.csv'


def read_csv_ids(path: Path, field: str):
    with path.open('r', encoding='utf-8-sig', newline='') as fh:
        return [int(row[field]) for row in csv.DictReader(fh)]


def parse_shop_items(text: str):
    parsed = []
    shops_seen = []
    for line in text.splitlines():
        if not line.startswith('-\tshop\tEA'):
            continue
        parts = line.split('\t')
        name = parts[2]
        inventory = parts[3].split(',', 1)[1]
        rows = []
        for pair in inventory.split(','):
            item_id, price = pair.split(':')
            rows.append((int(item_id), int(price)))
        shops_seen.append(name)
        parsed.extend((name, item_id, price) for item_id, price in rows)
        assert 1 <= len(rows) <= 40, (name, len(rows))
    return shops_seen, parsed


def balanced_script(text: str):
    cleaned = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i:i+2]
        if not in_string and nxt == '//':
            while i < len(text) and text[i] != '\n':
                i += 1
            cleaned.append('\n')
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            cleaned.append(' ')
        elif in_string:
            cleaned.append(' ')
        else:
            cleaned.append(ch)
        escape = (ch == '\\' and not escape)
        if ch != '\\':
            escape = False
        i += 1
    assert not in_string, 'unterminated string'
    cleaned = ''.join(cleaned)
    for left, right in [('(', ')'), ('{', '}')]:
        depth = 0
        for ch in cleaned:
            if ch == left:
                depth += 1
            elif ch == right:
                depth -= 1
                assert depth >= 0, f'unbalanced {left}{right}'
        assert depth == 0, f'unbalanced {left}{right}: {depth}'


source_ids = read_csv_ids(source_csv, 'Id')
nav_ids = read_csv_ids(nav_csv, 'ItemID')
assert len(source_ids) == 5885
assert len(source_ids) == len(set(source_ids))
assert nav_ids == list(dict.fromkeys(nav_ids)), 'navigation audit duplicates or order issue'
assert set(nav_ids) == set(source_ids)

shop_names, shop_rows = parse_shop_items(shops.read_text(encoding='utf-8'))
shop_ids = [row[1] for row in shop_rows]
assert len(shop_names) == 252
assert len(shop_names) == len(set(shop_names))
assert len(shop_ids) == 5885
assert len(shop_ids) == len(set(shop_ids))
assert set(shop_ids) == set(source_ids)

price_by_id = {}
with source_csv.open('r', encoding='utf-8-sig', newline='') as fh:
    for row in csv.DictReader(fh):
        price_by_id[int(row['Id'])] = int(row['ShopPrice'])
for _, item_id, price in shop_rows:
    assert price == price_by_id[item_id], (item_id, price, price_by_id[item_id])

manager_text = manager.read_text(encoding='utf-8')
balanced_script(manager_text)
assert '$@EA_ItemCount = 5885;' in manager_text
assert '$@EA_PageCount = 252;' in manager_text
assert 'Find by Item ID' in manager_text
assert 'callshop($@EA_PageShop$[.@page],1);' in manager_text
select_strings = re.findall(r'select\("([^"]*)"\)', manager_text)
assert select_strings and max(map(len, select_strings)) <= 255

function_defs = set(re.findall(r'^function\tscript\t([A-Za-z0-9_]+)\t\{', manager_text, re.M))
function_calls = set(re.findall(r'callfunc "([A-Za-z0-9_]+)"', manager_text))
assert function_calls <= function_defs, sorted(function_calls - function_defs)
static_shop_calls = set(re.findall(r'callshop "(EA[0-9]{4})",1;', manager_text))
assert static_shop_calls == set(shop_names), (len(static_shop_calls), len(shop_names))

buyer_text = buyer.read_text(encoding='utf-8')
balanced_script(buyer_text)
expected_materials = list(range(1001424, 1001437)) + list(range(25728, 25732))
material_block = re.search(r'setarray \.MaterialItems\[0\],(.*?);', buyer_text, re.S)
assert material_block
actual_materials = [int(x) for x in re.findall(r'\d+', material_block.group(1))]
assert actual_materials == expected_materials
assert '.MaterialPrice = 10000;' in buyer_text
assert '.@base_price = .MaterialPrice;' in buyer_text
assert 'Listed special materials pay ^0000FF12,400 Zeny each' in buyer_text

with material_audit.open('r', encoding='utf-8-sig', newline='') as fh:
    material_rows = list(csv.DictReader(fh))
assert [int(row['ItemID']) for row in material_rows] == expected_materials
assert all(int(row['SpecialBasePrice']) == 10000 for row in material_rows)
assert all(int(row['FinalUnitPayout']) == 12400 for row in material_rows)

print('EQUIPMENT ARCHIVE NAVIGATION VALIDATION PASSED')
print(f'Validated items: {len(source_ids)}')
print(f'Alphabetical shop pages: {len(shop_names)}')
print(f'Max select string length: {max(map(len, select_strings))}')
print(f'10,000-Zeny material tier IDs: {len(expected_materials)}')
