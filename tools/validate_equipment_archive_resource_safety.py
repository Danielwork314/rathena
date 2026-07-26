#!/usr/bin/env python3
from __future__ import annotations
import csv, re, sys
from pathlib import Path

KNOWN_BAD_IDS={490098,490376,490411,490418,490430,490436}
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
audit=root/'npc/custom/equipment_archive/audit'
inc_path=audit/'equipment_archive_included_full.csv'
exc_path=audit/'equipment_archive_regional_high_risk_excluded.csv'
shop_paths=[root/'npc/custom/equipment_archive/equipment_archive_low_level_shops.txt',root/'npc/custom/equipment_archive/equipment_archive_shops.txt']
errors=[]
with inc_path.open(encoding='utf-8-sig',newline='') as f: included=list(csv.DictReader(f))
ids={int(r['Id']) for r in included}
regional=[r for r in included if (r.get('ClientServerTag') or '').strip()]
for r in regional:
    if r.get('CompatibilityTier')!='regional_resource_reused':
        errors.append(f"regional item lacks reused-resource tier: {r['Id']}")
    if not (r.get('ResourceEvidenceIds') or '').strip():
        errors.append(f"regional item lacks non-region icon evidence: {r['Id']}")
    if r.get('Category')=='Headgear' and int(r.get('ClientClassNum') or 0)>0 and not (r.get('AppearanceEvidenceIds') or '').strip():
        errors.append(f"regional headgear lacks non-region ClassNum evidence: {r['Id']}")
    if r.get('Category')=='Weapons' and int(r.get('View') or 0)>0 and not (r.get('AppearanceEvidenceIds') or '').strip():
        errors.append(f"regional weapon lacks non-region View evidence: {r['Id']}")
for bad in KNOWN_BAD_IDS:
    if bad in ids: errors.append(f'known runtime-bad ID still included: {bad}')
shop_ids=[]
for path in shop_paths:
    text=path.read_text(encoding='utf-8')
    for line in text.splitlines():
        if '\tshop\t' not in line: continue
        payload=line.rsplit('\t',1)[-1]
        parts=payload.split(',')[1:]
        if len(parts)>40: errors.append(f'{path.name} shop exceeds 40 items')
        for part in parts:
            m=re.match(r'(\d+):',part)
            if m: shop_ids.append(int(m.group(1)))
if len(shop_ids)!=len(set(shop_ids)): errors.append('duplicate item ID across hidden shops')
if set(shop_ids)!=ids:
    errors.append(f'shop/audit mismatch shops={len(set(shop_ids))} audit={len(ids)}')
with exc_path.open(encoding='utf-8-sig',newline='') as f: excluded=list(csv.DictReader(f))
if not excluded: errors.append('regional high-risk exclusion audit is empty')
print(f'Included equipment: {len(included)}')
print(f'Regional resource-reused kept: {len(regional)}')
print(f'Regional high-risk excluded: {len(excluded)}')
print(f'Known runtime-bad included: {sorted(KNOWN_BAD_IDS & ids)}')
if errors:
    print('STATIC VALIDATION FAILED')
    for e in errors: print('-',e)
    raise SystemExit(1)
print('RESOURCE-SAFETY VALIDATION PASSED')
