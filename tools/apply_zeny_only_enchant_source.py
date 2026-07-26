#!/usr/bin/env python3
"""Patch rAthena's modern item enchant UI with a Zeny-only entry point.

The native item_enchant command remains unchanged. The new
item_enchant_zeny command preserves the native target-item, refine, grade,
slot-order, chance, reset and upgrade rules, but skips material checks and
material consumption for windows opened through that command.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


class PatchError(RuntimeError):
    pass


@dataclass
class TextFile:
    path: Path
    text: str
    newline: str
    bom: bool


def read_text_file(path: Path) -> TextFile:
    if not path.is_file():
        raise PatchError(f"Missing required file: {path}")
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    if bom:
        data = data[3:]
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"{path} is not UTF-8: {exc}") from exc
    newline = "\r\n" if "\r\n" in decoded else "\n"
    return TextFile(path=path, text=decoded.replace("\r\n", "\n"), newline=newline, bom=bom)


def write_text_file(file: TextFile, text: str) -> None:
    encoded_text = text if file.newline == "\n" else text.replace("\n", "\r\n")
    data = encoded_text.encode("utf-8")
    if file.bom:
        data = b"\xef\xbb\xbf" + data
    file.path.write_bytes(data)


def replace_exact(text: str, old: str, new: str, label: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise PatchError(f"{label}: expected {expected} matching block(s), found {count}")
    return text.replace(old, new)


def backup(path: Path) -> Path:
    destination = path.with_name(path.name + ".before_zeny_only_enchant")
    if not destination.exists():
        shutil.copy2(path, destination)
    return destination


def patch_clif_hpp(file: TextFile) -> str:
    text = file.text
    marker = "void clif_enchantwindow_open_zeny( map_session_data& sd, uint64 clientLuaIndex );"
    if marker in text:
        return text
    old = "void clif_enchantwindow_open( map_session_data& sd, uint64 clientLuaIndex );\n"
    new = old + marker + "\n"
    return replace_exact(text, old, new, "clif.hpp declaration")


def patch_clif_cpp(file: TextFile) -> str:
    text = file.text
    marker = "ITEM_ENCHANT_ZENY_ONLY_FLAG"
    if marker in text:
        return text

    old_open = '''void clif_enchantwindow_open( map_session_data& sd, uint64 clientLuaIndex ){
#if PACKETVER_RE_NUM >= 20211103 || PACKETVER_MAIN_NUM >= 20220330
\t// Hardcoded clientside check
\tif( pc_getpercentweight(sd) >= 70 ){
\t\tclif_msg_color( sd, MSI_ENCHANT_FAILED_OVER_WEIGHT, color_table[COLOR_RED] );
\t\tsd.state.item_enchant_index = 0;
\t\treturn;
\t\t
\t}

\tPACKET_ZC_UI_OPEN_V3 p = {};

\tp.packetType = HEADER_ZC_UI_OPEN_V3;
\tp.type = OUT_UI_ENCHANT;
\tp.data = clientLuaIndex;

\tclif_send( &p, sizeof( p ), &sd, SELF );

\tsd.state.item_enchant_index = clientLuaIndex;
#endif
}
'''

    new_open = '''static constexpr uint64 ITEM_ENCHANT_ZENY_ONLY_FLAG = static_cast<uint64>( 1 ) << 63;

static bool clif_enchantwindow_is_zeny_only( const map_session_data& sd ){
\treturn ( sd.state.item_enchant_index & ITEM_ENCHANT_ZENY_ONLY_FLAG ) != 0;
}

static uint64 clif_enchantwindow_group( const map_session_data& sd ){
\treturn sd.state.item_enchant_index & ~ITEM_ENCHANT_ZENY_ONLY_FLAG;
}

void clif_enchantwindow_open( map_session_data& sd, uint64 clientLuaIndex ){
#if PACKETVER_RE_NUM >= 20211103 || PACKETVER_MAIN_NUM >= 20220330
\t// Hardcoded clientside check
\tif( pc_getpercentweight(sd) >= 70 ){
\t\tclif_msg_color( sd, MSI_ENCHANT_FAILED_OVER_WEIGHT, color_table[COLOR_RED] );
\t\tsd.state.item_enchant_index = 0;
\t\treturn;
\t\t
\t}

\tPACKET_ZC_UI_OPEN_V3 p = {};

\tp.packetType = HEADER_ZC_UI_OPEN_V3;
\tp.type = OUT_UI_ENCHANT;
\tp.data = clientLuaIndex;

\tclif_send( &p, sizeof( p ), &sd, SELF );

\t// Opening a native window always clears any previous custom mode flag.
\tsd.state.item_enchant_index = clientLuaIndex;
#endif
}

void clif_enchantwindow_open_zeny( map_session_data& sd, uint64 clientLuaIndex ){
#if PACKETVER_RE_NUM >= 20211103 || PACKETVER_MAIN_NUM >= 20220330
\tclif_enchantwindow_open( sd, clientLuaIndex );

\t// The plain group ID is sent to the client. The high bit is server-only state.
\tif( sd.state.item_enchant_index == clientLuaIndex ){
\t\tsd.state.item_enchant_index |= ITEM_ENCHANT_ZENY_ONLY_FLAG;
\t}
#endif
}
'''
    text = replace_exact(text, old_open, new_open, "clif.cpp enchant window open")

    old_compare = "\tif( sd->state.item_enchant_index != p->enchant_group ){\n"
    new_compare = "\tif( clif_enchantwindow_group( *sd ) != p->enchant_group ){\n"
    text = replace_exact(text, old_compare, new_compare, "enchant group checks", expected=4)

    material_blocks = [
        (
'''\tfor( const auto& entry : enchant_slot->normal.materials ){
\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\tif( idx < 0 ){
\t\t\treturn;
\t\t}

\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\treturn;
\t\t}

\t\tmaterials[idx] = entry.second;
\t}
''',
'''\tif( !clif_enchantwindow_is_zeny_only( *sd ) ){
\t\tfor( const auto& entry : enchant_slot->normal.materials ){
\t\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\t\tif( idx < 0 ){
\t\t\t\treturn;
\t\t\t}

\t\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\t\treturn;
\t\t\t}

\t\t\tmaterials[idx] = entry.second;
\t\t}
\t}
''', "random enchant materials"),
        (
'''\tfor( const auto& entry : perfect_enchant->materials ){
\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\tif( idx < 0 ){
\t\t\treturn;
\t\t}

\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\treturn;
\t\t}

\t\tmaterials[idx] = entry.second;
\t}
''',
'''\tif( !clif_enchantwindow_is_zeny_only( *sd ) ){
\t\tfor( const auto& entry : perfect_enchant->materials ){
\t\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\t\tif( idx < 0 ){
\t\t\t\treturn;
\t\t\t}

\t\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\t\treturn;
\t\t\t}

\t\t\tmaterials[idx] = entry.second;
\t\t}
\t}
''', "perfect enchant materials"),
        (
'''\tfor( const auto& entry : upgrade->materials ){
\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\tif( idx < 0 ){
\t\t\treturn;
\t\t}

\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\treturn;
\t\t}

\t\tmaterials[idx] = entry.second;
\t}
''',
'''\tif( !clif_enchantwindow_is_zeny_only( *sd ) ){
\t\tfor( const auto& entry : upgrade->materials ){
\t\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\t\tif( idx < 0 ){
\t\t\t\treturn;
\t\t\t}

\t\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\t\treturn;
\t\t\t}

\t\t\tmaterials[idx] = entry.second;
\t\t}
\t}
''', "upgrade enchant materials"),
        (
'''\tfor( const auto& entry : enchant->reset.materials ){
\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\tif( idx < 0 ){
\t\t\treturn;
\t\t}

\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\treturn;
\t\t}

\t\tmaterials[idx] = entry.second;
\t}
''',
'''\tif( !clif_enchantwindow_is_zeny_only( *sd ) ){
\t\tfor( const auto& entry : enchant->reset.materials ){
\t\t\tint16 idx = pc_search_inventory( sd, entry.first );

\t\t\tif( idx < 0 ){
\t\t\t\treturn;
\t\t\t}

\t\t\tif( sd->inventory.u.items_inventory[idx].amount < entry.second ){
\t\t\t\treturn;
\t\t\t}

\t\t\tmaterials[idx] = entry.second;
\t\t}
\t}
''', "reset enchant materials"),
    ]

    for old, new, label in material_blocks:
        text = replace_exact(text, old, new, label)

    if text.count("clif_enchantwindow_is_zeny_only( *sd )") != 4:
        raise PatchError("clif.cpp sanity check failed: four material guards were not created")
    if text.count("clif_enchantwindow_group( *sd )") != 4:
        raise PatchError("clif.cpp sanity check failed: four masked group checks were not created")
    return text


def patch_script_cpp(file: TextFile) -> str:
    text = file.text
    if "BUILDIN_FUNC(item_enchant_zeny)" in text:
        return text

    native = '''BUILDIN_FUNC(item_enchant){
#if !( PACKETVER_RE_NUM >= 20211103 || PACKETVER_MAIN_NUM >= 20220330 )
\tShowError( "buildin_item_enchant: This command requires packet version 2021-11-03 or newer.\\n" );
\treturn SCRIPT_CMD_FAILURE;
#else
\tmap_session_data* sd;

\tif( !script_charid2sd( 3, sd ) ){
\t\treturn SCRIPT_CMD_FAILURE;
\t}

\tuint64 clientLuaIndex = script_getnum64( st, 2 );

\tif( !item_enchant_db.exists( clientLuaIndex ) ){
\t\tShowError( "buildin_item_enchant: %" PRIu64 " is not a valid item enchant index.\\n", clientLuaIndex );
\t\treturn SCRIPT_CMD_FAILURE;
\t}

\tclif_enchantwindow_open( *sd, clientLuaIndex );

\treturn SCRIPT_CMD_SUCCESS;
#endif
}
'''

    custom = native + '''
BUILDIN_FUNC(item_enchant_zeny){
#if !( PACKETVER_RE_NUM >= 20211103 || PACKETVER_MAIN_NUM >= 20220330 )
\tShowError( "buildin_item_enchant_zeny: This command requires packet version 2021-11-03 or newer.\\n" );
\treturn SCRIPT_CMD_FAILURE;
#else
\tmap_session_data* sd;

\tif( !script_charid2sd( 3, sd ) ){
\t\treturn SCRIPT_CMD_FAILURE;
\t}

\tuint64 clientLuaIndex = script_getnum64( st, 2 );

\tif( !item_enchant_db.exists( clientLuaIndex ) ){
\t\tShowError( "buildin_item_enchant_zeny: %" PRIu64 " is not a valid item enchant index.\\n", clientLuaIndex );
\t\treturn SCRIPT_CMD_FAILURE;
\t}

\tclif_enchantwindow_open_zeny( *sd, clientLuaIndex );

\treturn SCRIPT_CMD_SUCCESS;
#endif
}
'''
    text = replace_exact(text, native, custom, "script.cpp item_enchant command")

    old_def = '\tBUILDIN_DEF(item_enchant, "i?"),\n'
    new_def = old_def + '\tBUILDIN_DEF(item_enchant_zeny, "i?"),\n'
    text = replace_exact(text, old_def, new_def, "script.cpp command registration")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", default=".", help="rAthena repository root")
    parser.add_argument("--check", action="store_true", help="validate applicability without writing")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    files = {
        "clif_hpp": read_text_file(root / "src/map/clif.hpp"),
        "clif_cpp": read_text_file(root / "src/map/clif.cpp"),
        "script_cpp": read_text_file(root / "src/map/script.cpp"),
    }

    already = (
        "clif_enchantwindow_open_zeny" in files["clif_hpp"].text
        and "ITEM_ENCHANT_ZENY_ONLY_FLAG" in files["clif_cpp"].text
        and "BUILDIN_FUNC(item_enchant_zeny)" in files["script_cpp"].text
    )
    partial = any((
        "clif_enchantwindow_open_zeny" in files["clif_hpp"].text,
        "ITEM_ENCHANT_ZENY_ONLY_FLAG" in files["clif_cpp"].text,
        "BUILDIN_FUNC(item_enchant_zeny)" in files["script_cpp"].text,
    )) and not already

    if already:
        print("Zeny-only item enchant source support is already installed.")
        return 0
    if partial:
        raise PatchError("A partial Zeny-only enchant source modification already exists; restore or review it before retrying.")

    patched = {
        "clif_hpp": patch_clif_hpp(files["clif_hpp"]),
        "clif_cpp": patch_clif_cpp(files["clif_cpp"]),
        "script_cpp": patch_script_cpp(files["script_cpp"]),
    }

    if args.check:
        print("Source patch applicability check: PASS")
        return 0

    for key, file in files.items():
        backup_path = backup(file.path)
        write_text_file(file, patched[key])
        print(f"Updated {file.path}")
        print(f"Backup  {backup_path}")

    print("Source patch applied successfully. Rebuild and restart map-server.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
