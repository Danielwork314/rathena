SHADOW CAPSULE SCOPE FIX
The job-tier version originally selected .@item inside S_Draw_* and then called
S_Award without arguments. rAthena starts a new .@ variable scope for callsub,
so S_Award received item ID 0 and checkweight(0,1) returned false.

This package passes the selected Item ID and price explicitly:
   callsub S_Award,.@item,.@price;

S_Award receives them through getarg(0) and getarg(1). It also now distinguishes
invalid reward, overweight, no free inventory slot, and insufficient Zeny.

rAthena Equipment Archive - Active ItemInfo and Shadow Job Tiers

FIXES
1. Unknown Item:
   The previous package used System/itemInfo_true.lub as its client allowlist.
   Your actual English client loads SystemEN/LuaFiles514/itemInfo.lua.
   This package uses the active file and removes another
   67 unsupported entries.

2. Shadow Capsule:
   Shadow gear is now grouped into:
   - General Shadows
   - Second / Expanded Jobs
   - Third / Advanced Jobs
   - Fourth Jobs

   After selecting a tier, select the job family, then:
   - Any slot: 100,000 Zeny
   - Selected slot: 300,000 Zeny

   Third/Fourth-compatible shared items appear in both eligible menus.

NPC LOCATIONS
- Equipment Archive: prontera 153,227
- Costume Capsule: prontera 155,227
- Shadow Capsule: prontera 157,227
- Pet Archive: prontera 159,227
- Card Remover: prontera 139,225
- Center line: prontera 156,227

FINAL COUNTS
- Ordinary equipment: 1,488
- Costumes: 1,498
- Shadow gear: 963
- Pet eggs: 130
- Pet equipment: 25
- Total: 4,104

LOCAL APPLY
1. Extract into:
   C:\xampp\htdocs\rathena

2. Review:
   cd C:\xampp\htdocs\rathena
   git status --short
   git --no-pager diff --check
   git --no-pager diff --stat
   git --no-pager diff -- npc/scripts_custom.conf npc/custom/equipment_archive

3. Stage:
   git add npc/scripts_custom.conf
   git add npc/custom/equipment_archive
git add npc/custom/card_remover.txt

4. Commit and push:
   git commit -m "Fix shadow gacha reward scope"
   git push origin master

LIVE APPLY
   cd /opt/rathena
   git status --short
   git pull --ff-only
   sudo ./athena-start restart

SMOKE TEST
- Open Headgear > Lv 200+ and check every page for Unknown Item.
- Open at least one other Lv 200+ equipment category.
- Open Shadow Capsule.
- Check General Shadows.
- Check Second / Expanded Jobs.
- Check Third / Advanced Jobs, including Royal Guard.
- Check Fourth Jobs, including Imperial Guard.
- Draw from Any Slot and one selected slot.
- Confirm one draw deducts Zeny exactly once.
- Confirm no script parse errors in map-server logs.

AUDIT FILES
- manifests/included_active_iteminfo_items.csv
- manifests/excluded_active_iteminfo_unknown_items.csv
- manifests/excluded_risky_items.csv
- manifests/shadow_job_tier_pools.csv

ROLLBACK
Before commit:
   git restore npc/scripts_custom.conf
   git restore npc/custom/equipment_archive

After commit:
   git revert <commit-sha>
   git push origin master

Live:
   cd /opt/rathena
   git pull --ff-only
   sudo ./athena-start restart
