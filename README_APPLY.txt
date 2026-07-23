rAthena Equipment Archive NPC Update

CONTENTS
- Equipment Archive: 2,910 high-level ordinary equipment items.
- Costume Capsule: 3,183 costume items.
- Shadow Capsule: 963 shadow items.
- Pet Archive: 149 pet eggs and 28 pet equipment items.
- Safety-excluded: 467 items, listed in manifests/excluded_risky_items.csv.

NPC LOCATIONS
- Equipment Archive: prontera 153,227
- Costume Capsule: prontera 155,227
- Shadow Capsule: prontera 157,227
- Pet Archive: prontera 159,227
- Center line: prontera 156,227

PRICES
- Ordinary Lv100-129: 200,000 Zeny
- Ordinary Lv130-159: 500,000 Zeny
- Ordinary Lv160-199: 1,000,000 Zeny
- Ordinary Lv200+: 2,000,000 Zeny
- Costume draw: 100,000 Zeny
- Shadow all-slot draw: 100,000 Zeny
- Shadow selected-slot draw: 300,000 Zeny
- Pet egg: 200,000 Zeny
- Pet equipment: 100,000 Zeny

LOCAL APPLY
1. Extract the package into the local rAthena repository root:
   C:\xampp\htdocs\rathena

2. Review:
   git status --short
   git --no-pager diff --check
   git --no-pager diff --stat
   git --no-pager diff -- npc/scripts_custom.conf npc/custom/equipment_archive

3. Stage only the generated files:
   git add npc/scripts_custom.conf
   git add npc/custom/equipment_archive

4. Commit and push:
   git commit -m "Add equipment archive shops and gacha NPCs"
   git push origin master

LIVE APPLY
1. Pull:
   cd /opt/rathena
   git status --short
   git pull --ff-only

2. Restart to perform a clean full script parse:
   sudo ./athena-start restart

3. Watch the map-server console/log for script parse errors.

MANUAL SMOKE TEST
- Talk to Equipment Archive and open one page in every ordinary category.
- Buy one item from each price tier.
- Draw once from every Costume Capsule category.
- Draw once from all-slot and every selected Shadow Capsule category.
- Buy one pet egg and one pet equipment item.
- Test insufficient Zeny.
- Test a full inventory.
- Confirm the Zeny deduction occurs exactly once.
- Confirm NPC draw entries appear in the NPC log through logmes.

ROLLBACK
LOCAL before commit:
   git restore npc/scripts_custom.conf
   Remove-Item -Recurse -Force npc\custom\equipment_archive

AFTER COMMIT:
   git revert <commit-sha>
   git push origin master

LIVE:
   cd /opt/rathena
   git pull --ff-only
   sudo ./athena-start restart

NOTES
- The source database ZIP does not include the client ItemInfo files.
- Every included ID was validated against the server item database, but client icon/name
  compatibility must be confirmed during the smoke test.
- Gacha duplicates are intentionally allowed.
- Items with Trade.NoStorage=true and clearly marked Rental/Trial items are excluded
  so players are not trapped with unsafe rewards. See the excluded manifest.
