#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'db/re/item_enchant.yml'
text = PATH.read_text(encoding='utf-8')
start = text.index('  - Id: 156\n')
end = text.index('\n  - Id: 157\n', start)
block = text[start:end]

assert 'Yorscalp_P_Circlet: true' in block
assert 'Yorscalp_M_Circlet: true' in block

expected = {
    3: [('Strength5', 25000), ('Inteligence5', 25000), ('Vitality5', 25000), ('Luck5', 25000)],
    2: [('Yorscalp_Str4', 20000), ('Yorscalp_Int4', 20000), ('Yorscalp_Smart4', 20000), ('Yorscalp_Speed4', 20000), ('Yorscalp_Def4', 20000)],
}

# Split only the random slot portions, before Slot 1 perfect enchants.
slot_markers = list(re.finditer(r'^      - Slot: (\d+)\n', block, re.M))
slots = {}
for idx, m in enumerate(slot_markers):
    slot = int(m.group(1))
    s = m.start()
    e = slot_markers[idx+1].start() if idx+1 < len(slot_markers) else len(block)
    slots[slot] = block[s:e]

for slot in (3, 2):
    sb = slots[slot]
    grade_blocks = re.findall(r'          - Enchantgrade: (\d+)\n            Items:\n(.*?)(?=          - Enchantgrade:|\Z)', sb, re.S)
    assert len(grade_blocks) == 5, (slot, len(grade_blocks))
    for grade, items_text in grade_blocks:
        pairs = [(name, int(chance)) for name, chance in re.findall(r'              - Item: ([^\n]+)\n                Chance: (\d+)', items_text)]
        assert pairs == expected[slot], (slot, grade, pairs)
        assert sum(chance for _, chance in pairs) == 100000, (slot, grade)

# Ensure all lower-tier random outcomes are absent from group 156.
for forbidden in [
    'Strength1','Strength2','Strength3','Strength4',
    'Inteligence1','Inteligence2','Inteligence3','Inteligence4',
    'Vitality1','Vitality2','Vitality3','Vitality4',
    'Luck1','Luck2','Luck3','Luck4',
    'Yorscalp_Str1','Yorscalp_Str2','Yorscalp_Str3',
    'Yorscalp_Int1','Yorscalp_Int2','Yorscalp_Int3',
    'Yorscalp_Smart1','Yorscalp_Smart2','Yorscalp_Smart3',
    'Yorscalp_Speed1','Yorscalp_Speed2','Yorscalp_Speed3',
    'Yorscalp_Def1','Yorscalp_Def2','Yorscalp_Def3',
]:
    assert re.search(rf'\b{re.escape(forbidden)}\b', block) is None, forbidden

assert 'Arbiter_Warrant' in slots[1]
assert 'Bailiff_Warrant' in slots[1]
assert 'Reset:' in block

print('YORSCALP CROWN MAX-RANDOM VALIDATION PASSED')
print('Target crowns: physical + magical')
print('Slot 3: 4 maximum-stat outcomes, 25% each')
print('Slot 2: 5 Lv.4 outcomes, 20% each')
print('Slot 1: Arbiter/Bailiff perfect choices preserved')
print('Reset: preserved')
