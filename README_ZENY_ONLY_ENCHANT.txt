Zeny-only Enchant Database Manager
==================================

目的
----
只把自定义 Enchant Database Manager 改成免材料、只收官方 Zeny 价格。

保留不变：
- 允许附魔的装备名单
- 最低精炼要求
- 最低阶级要求
- 附魔槽顺序
- 随机附魔池与原本成功率
- 指定附魔选项
- 附魔升级路线
- 重置成功率与失败规则
- 官方 Zeny 费用

不会改变：
- 原本官方 item_enchant() NPC 仍然检查并消耗材料
- 旧的自定义 Zeny-only 附魔 NPC 不受影响

变更内容
--------
1. NPC 改用新脚本命令：

   item_enchant_zeny(<group id>);

2. map-server 新增独立的 Zeny-only 模式：
   - 仅由 item_enchant_zeny() 开启
   - 跳过材料数量检查
   - 不删除材料
   - 仍然扣除数据库原本规定的 Zeny

安装
----
在 rAthena 仓库根目录执行：

1. 先检查源代码能否自动修改：

   python3 tools/apply_zeny_only_enchant_source.py /opt/rathena --check

2. 检查通过后应用：

   python3 tools/apply_zeny_only_enchant_source.py /opt/rathena

   脚本会自动备份：
   - src/map/clif.hpp.before_zeny_only_enchant
   - src/map/clif.cpp.before_zeny_only_enchant
   - src/map/script.cpp.before_zeny_only_enchant

3. 把更新包中的 NPC 文件覆盖到仓库：

   npc/custom/enchant/enchant_database_manager.txt

4. 重新编译 map-server：

   cd /opt/rathena
   make clean
   make -j2 map

   如果你的 Makefile 不支持单独的 map 目标，则使用：

   make -j2 server

5. 完整重启 map-server。

   这次修改包含 C++ 源代码，只有 @reloadscript 不够。

验证
----
1. 身上不要携带目标附魔所列的任何材料。
2. 准备足够 Zeny 与符合要求的装备。
3. 与 Prontera 156,176 的 Enchant Database Manager 对话。
4. 选择一个附魔组，例如：
   - 152：Yorscalp Armor / Robe
   - 153：Yorscalp Manteau / Muffler
   - 154：Yorscalp Boots / Shoes
   - 155：Yorscalp Accessories
   - 156：Yorscalp Crowns
5. 完成一次普通、指定、升级或重置附魔。
6. 确认：
   - Zeny 正确减少
   - 材料数量没有减少
   - 没有材料也能完成请求
   - 装备、精炼、阶级和槽位限制仍然有效
7. 再测试一个原本官方附魔 NPC，确认它仍需要材料。

客户端显示说明
--------------
Enchant UI 的说明内容来自客户端 EnchantList.lub，因此窗口仍可能显示官方材料图示或数量。
本更新修改的是服务器验证和消耗逻辑：通过这个自定义 NPC 开启时，服务器不会要求或消耗这些材料。

如果你的特定客户端在材料为 0 时直接把确认按钮锁死，服务器无法收到请求；这种情况还需要按你实际客户端的 EnchantList.lub 制作对应的客户端覆盖文件。不要使用其他版本的 EnchantList.lub 整份覆盖，否则可能破坏现有附魔组。

回退
----
停止服务器后执行：

   cd /opt/rathena
   cp src/map/clif.hpp.before_zeny_only_enchant src/map/clif.hpp
   cp src/map/clif.cpp.before_zeny_only_enchant src/map/clif.cpp
   cp src/map/script.cpp.before_zeny_only_enchant src/map/script.cpp
   make clean
   make -j2 map

然后把旧版 enchant_database_manager.txt 覆盖回来并重启。

手动方式
--------
patches/item_enchant_zeny_only.patch 仅供审查或在自动修改器无法匹配时手动应用：

   git apply --check patches/item_enchant_zeny_only.patch
   git apply patches/item_enchant_zeny_only.patch

如果仓库已有自定义 source 改动，优先使用 Python 修改器，因为它只修改相关原生代码块并保留其他改动。
