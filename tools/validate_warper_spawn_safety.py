#!/usr/bin/env python3
"""Validate that the custom warper does not expose known unimplemented maps."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WARPER = ROOT / "npc" / "custom" / "warper.txt"

FORBIDDEN_TOKENS = (
    # Episode/map assets exist, but this repository does not load their monster/content scripts.
    '"Frozen Scale Fields",F10',
    '"Issgard Dungeon",D24',
    'jor_back1',
    'jor_back2',
    'jor_back3',
    'jor_tail',
    'jor_ab01',
    'jor_ab02',
    'jor_dun01',
    'jor_dun02',
    'clock_01',
    'abyss_04',
    'ecl_tdun04',
    'ice_dun04',
    'Unknown Basement',
    'bl_death',
    'bl_lava',
    'bl_grass',
    'bl_ice',
)

REQUIRED_SNIPPETS = (
    'Disp("Abyss Lakes",1,3); Pick("abyss_");',
    'Disp("Bifrost Tower",1,3); Pick("ecl_tdun");',
    'Disp("Ice Dungeon",1,3); Pick("ice_dun");',
    'Restrict("RE",9,10);',
    'Pick("","c_tower1","c_tower2","c_tower3","c_tower4","alde_dun01","alde_dun02","alde_dun03","alde_dun04","c_tower2_","c_tower3_");',
    'Disp("Sewage Treatment Plant:1st Power Plant:2nd Power Plant:Large Bath Meditathio:Lost Farm Valley:Library Memory Corridor:Upper Floor of Tartaros Storage:Lower Floor of Tartaros Storage");',
    'Pick("","ba_pw02","ba_pw01","ba_pw03","ba_bath","ba_lost","ba_lib","ba_2whs01","ba_2whs02");',
    'Disp("Garden of Time Entrance:Spirit Sanctuary Area 1:Spirit Sanctuary Area 2");',
)


def main() -> int:
    if not WARPER.is_file():
        print(f"ERROR: warper file not found: {WARPER}", file=sys.stderr)
        return 1

    text = WARPER.read_text(encoding="ascii")
    errors: list[str] = []

    for token in FORBIDDEN_TOKENS:
        if token in text:
            errors.append(f"unimplemented destination is still exposed: {token}")

    for snippet in REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"expected safe warper configuration is missing: {snippet}")

    if 'Disp("Garden of Time:Spirit Sanctuary Area 1:Spirit Sanctuary Area 2");' in text:
        errors.append("Garden of Time control map is not labelled as an entrance")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Warper spawn-safety validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
