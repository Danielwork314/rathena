rAthena Equipment Archive - Client-Compatible Update

ROOT CAUSE
The previous package contained 7,233 server-valid items.
The uploaded active client file, System/itemInfo_true.lub, supports only 4,171
of those items. The other 3,062 entries were removed because the client would
show them as Unknown Item or had a blank client name/resource.

NPC LOCATIONS
- Equipment Archive: prontera 153,227
- Costume Capsule: prontera 155,227
- Shadow Capsule: prontera 157,227
- Pet Archive: prontera 159,227
- Center line: prontera 156,227

FINAL COUNTS
- Ordinary equipment: 1,521
- Costumes: 1,532
- Shadow gear: 963
- Pet eggs: 130
- Pet equipment: 25
- Total: 4,171

LOCAL APPLY
1. Extract this ZIP into:
   C:\xampp\htdocs\rathena

2. Review:
   cd C:\xampp\htdocs\rathena
   git status --short
   git --no-pager diff --check
   git --no-pager diff --stat
   git --no-pager diff -- npc/scripts_custom.conf npc/custom/equipment_archive

3. Stage only:
   git add npc/scripts_custom.conf
   git add npc/custom/equipment_archive

4. Commit and push:
   git commit -m "Filter equipment archive by client ItemInfo"
   git push origin master

LIVE APPLY
   cd /opt/rathena
   git status --short
   git pull --ff-only
   sudo ./athena-start restart

SMOKE TEST
- Open at least one shop page in each ordinary category.
- Confirm no Unknown Item rows appear.
- Draw from every Costume Capsule category.
- Draw from all Shadow Capsule categories.
- Buy one pet egg and one pet equipment item.
- Test insufficient Zeny and a full inventory.
- Confirm one draw deducts Zeny exactly once.

AUDIT FILES
- manifests/included_client_supported_items.csv
- manifests/excluded_client_unknown_items.csv
- manifests/excluded_risky_items.csv

ROLLBACK
Local before commit:
   git restore npc/scripts_custom.conf
   Remove-Item -Recurse -Force npc\custom\equipment_archive

After commit:
   git revert <commit-sha>
   git push origin master

Live:
   cd /opt/rathena
   git pull --ff-only
   sudo ./athena-start restart
