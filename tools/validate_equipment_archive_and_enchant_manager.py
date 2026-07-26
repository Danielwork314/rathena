#!/usr/bin/env python3
from __future__ import annotations
import csv, json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / 'npc/custom/equipment_archive'
ITEM_PAIR = re.compile(r'(\d+):(\d+)')
SHOP_DEF = re.compile(r'^-\tshop\t([^\t]+)\t-1,(.+)$')
CALLSHOP = re.compile(r'callshop\s+"([^"]+)"')
FUNCTION = re.compile(r'^function\tscript\t([^\t]+)\t\{', re.M)
CALLFUNC = re.compile(r'callfunc\s+"([^"]+)"')
SELECT = re.compile(r'select\("([^"]*)"\)')

errors=[]
shop_defs={}
shop_ids=[]
for filename in ('equipment_archive_low_level_shops.txt','equipment_archive_shops.txt'):
    path=EA/filename
    for lineno,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        m=SHOP_DEF.match(line)
        if not m:
            continue
        name,payload=m.groups()
        if name in shop_defs:
            errors.append(f'duplicate shop {name}')
        pairs=[]
        for raw in payload.split(','):
            im=ITEM_PAIR.fullmatch(raw.strip())
            if not im:
                errors.append(f'{path}:{lineno}: invalid pair {raw!r}')
                continue
            pairs.append((int(im.group(1)),int(im.group(2))))
        if not 1 <= len(pairs) <= 40:
            errors.append(f'{name}: item count {len(pairs)} outside 1..40')
        shop_defs[name]=pairs
        shop_ids.extend(i for i,_ in pairs)

if len(shop_ids) != len(set(shop_ids)):
    duplicates=[i for i,c in Counter(shop_ids).items() if c>1]
    errors.append(f'duplicate item IDs in shops: {duplicates[:20]}')

included_path=EA/'audit/equipment_archive_included_full.csv'
with included_path.open(encoding='utf-8-sig',newline='') as f:
    included=list(csv.DictReader(f))
included_ids={int(row['Id']) for row in included}
if set(shop_ids) != included_ids:
    errors.append(f'shop/audit ID mismatch: shops-only={len(set(shop_ids)-included_ids)}, audit-only={len(included_ids-set(shop_ids))}')
regional_rows=[row for row in included if (row.get('ClientServerTag') or '').strip()]
if regional_rows:
    errors.append(f'regional Server-tagged entries still included: {len(regional_rows)}')
if 490098 in included_ids:
    errors.append('490098 Ring of Pazuzu (jRO) is still included')
if 410345 in included_ids:
    errors.append('410345 Clown_Smiling_ / Smiling Eyes (iRO) is still included')
if any((row.get('ClientResource') or '').strip() == 'Record_Mage2_TW' for row in included):
    errors.append('known runtime-bad resource Record_Mage2_TW is still included')

script_paths=[EA/'equipment_archive_low_level_menu.txt',EA/'equipment_archive_manager.txt']
all_script='\n'.join(p.read_text(encoding='utf-8-sig') for p in script_paths)
functions=FUNCTION.findall(all_script)
if len(functions)!=len(set(functions)):
    errors.append('duplicate Equipment Archive function definitions')
for target in CALLSHOP.findall(all_script):
    if target not in shop_defs:
        errors.append(f'callshop target missing: {target}')
for target in CALLFUNC.findall(all_script):
    if target not in set(functions):
        errors.append(f'callfunc target missing: {target}')
for menu in SELECT.findall(all_script):
    option_count=len(menu.split(':'))
    if option_count>10:
        errors.append(f'select has {option_count} options (>10): {menu[:100]}')

custom_conf=(ROOT/'npc/scripts_custom.conf').read_text(encoding='utf-8-sig')
for required in (
    'npc: npc/custom/equipment_archive/equipment_archive_shops.txt',
    'npc: npc/custom/equipment_archive/equipment_archive_low_level_shops.txt',
    'npc: npc/custom/equipment_archive/equipment_archive_low_level_menu.txt',
    'npc: npc/custom/equipment_archive/equipment_archive_manager.txt',
    'npc: npc/custom/enchant/enchant_database_manager.txt',
    'npc: npc/custom/enchant/enchant_database_manager_backend.txt',
):
    if custom_conf.count(required)!=1:
        errors.append(f'import count for {required}: {custom_conf.count(required)}')

frontend=(ROOT/'npc/custom/enchant/enchant_database_manager.txt').read_text(encoding='utf-8-sig')
backend=(ROOT/'npc/custom/enchant/enchant_database_manager_backend.txt').read_text(encoding='utf-8-sig')
if 'prontera,156,168,4\tscript\tEnchant Database Manager#custom_db' not in frontend:
    errors.append('Enchant Database Manager coordinate/declaration missing')
if re.search(r'(?m)^\s*item_enchant_zeny\s*\(', frontend):
    errors.append('frontend must not execute the custom source command')
if backend.count('item_enchant_zeny(.@id);')!=1:
    errors.append('backend source command call missing/duplicated')
if '$@EnchantDBManagerBackendReady = 0;' not in frontend or '$@EnchantDBManagerBackendReady = 1;' not in backend:
    errors.append('backend readiness diagnostic handshake missing')

# Simple delimiter balance outside quoted strings/comments is intentionally conservative.
for path in script_paths+[ROOT/'npc/custom/enchant/enchant_database_manager.txt',ROOT/'npc/custom/enchant/enchant_database_manager_backend.txt']:
    text=path.read_text(encoding='utf-8-sig')
    if text.count('{')!=text.count('}'):
        errors.append(f'{path}: brace imbalance {text.count("{")} != {text.count("}")}')

summary=json.loads((EA/'audit/equipment_archive_full_summary.json').read_text(encoding='utf-8'))
print(f"Equipment Archive IDs: {len(shop_ids)}")
print(f"Low / high: {summary['included_low_level']} / {summary['included_high_level']}")
print(f"Hidden shops: {len(shop_defs)}")
print(f"Functions: {len(functions)}")
print(f"Regional Server-tagged included: {len(regional_rows)}")
print(f"490098 Ring of Pazuzu included: {490098 in included_ids}")
print(f"410345 Smiling Eyes included: {410345 in included_ids}")
print(f"Enchant frontend imported and diagnostic backend isolated: {'yes' if not errors else 'check errors'}")
if errors:
    print('VALIDATION FAILED:')
    for error in errors:
        print('-',error)
    raise SystemExit(1)
print('STATIC VALIDATION PASSED')
