# ReactiveSuspects r12 — 安装 / Installation

## 中文

嫌疑人被子弹击中，或附近开火方向经过时，向真实射手反击，并尝试侧移、推进或追近。感应半径 2.5 米，前方方向通道最长 100 米；新事件刷新 8 秒反击时限。

主机安装即可。2026-10-30 玩家确认客机测试正常。移动受原版导航限制，实际穿墙效果受原版弹道和材质限制。

1. 确保主机 UE4SS 可以正常运行，然后关闭游戏。本包不包含加载器 DLL。
2. 将本包中的 Mods/ReactiveSuspects 放进实际正在加载的 UE4SS Mods 目录。本次测试使用 ReadyOrNot/Binaries/Win64/Mods。
3. 确认 Scripts/main.lua 和 enabled.txt 存在；如果 mods.txt 显式停用了 ReactiveSuspects，请改为启用。
4. 启动游戏，日志应显示 READY r12、movement=true 和三个 SHOT_HOOK_READY。客机无需安装本模组。

Install.ps1 可通过 -ModsDirectory 参数安装，并先完整备份已有的同名模组。停用时关闭游戏，将 ReactiveSuspects 文件夹移出 Mods。

配置在 Scripts/main.lua 顶部的 Config 中，修改后重启生效。感应通道不按墙面截断，它是射击方向感应近似，不是逐帧实体子弹轨迹。单机未命中反击和可见移动已实测；联机结果来自玩家反馈。

完整中英文说明、源码与校验值：
https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang

## English

Suspects retaliate toward the real shooter when hit or when a nearby firing direction is detected, while attempting native sidesteps, advances, or pursuit. The sensing radius is 2.5 m, the forward corridor is up to 100 m long, and new events refresh an 8-second retaliation window.

Install on the host only. The player confirmed normal client behavior on 2026-10-30. Movement is subject to native navigation; actual penetration depends on the game's ballistics and materials.

1. Make sure UE4SS works on the host, then close the game. Loader DLLs are not included.
2. Copy Mods/ReactiveSuspects into your active UE4SS Mods directory. The tested setup uses ReadyOrNot/Binaries/Win64/Mods.
3. Check that Scripts/main.lua and enabled.txt exist. If mods.txt explicitly disables ReactiveSuspects, enable that entry.
4. Start the game and look for READY r12, movement=true, and three SHOT_HOOK_READY entries. Clients do not need this mod.

Alternatively, use Install.ps1 with -ModsDirectory. It fully backs up an existing copy before installing. To disable the mod, close the game and move the ReactiveSuspects folder out of Mods.

Settings are in Config at the top of Scripts/main.lua and take effect after restarting. Walls do not clip the sensing corridor; this is shot-direction proximity sensing, not a frame-by-frame physical bullet track. Missed-shot retaliation and visible movement were tested locally; multiplayer results are player-reported.

Full bilingual instructions, source, and checksums:
https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang
