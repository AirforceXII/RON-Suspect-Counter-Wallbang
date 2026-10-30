# RON Suspect Counter-Wallbang — ReactiveSuspects r12

[中文](#中文) | [English](#english)

## 中文

《严阵以待》UE4SS 嫌疑人反击模组。嫌疑人被子弹击中，或检测到附近射击方向经过时，会立即朝真实射手的位置反击，即使双方被门或墙遮挡；反击时尝试侧移、推进或沿原版导航追近目标。

**主机安装即可。**单机未命中反击和移动已实测；2026-10-30 玩家确认客机测试正常。联机结论来自玩家反馈，详见[联机记录](evidence/r12-live/multiplayer-feedback.json)。

### 下载

- [r12 模组 ZIP](https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang/raw/refs/heads/main/output/ReactiveSuspects-r12-HostOnly-UE4SS.zip)
- [r12 完整源码 ZIP](https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang/raw/refs/heads/main/output/ReactiveSuspects-r12-Source.zip)
- [SHA-256 校验值](output/SHA256SUMS.txt)
- [直接浏览 Lua 源码](package/Mods/ReactiveSuspects/Scripts/main.lua)

### 安装与停用

1. 主机先安装能正常运行的 [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS/releases)，然后关闭游戏。模组 ZIP 不包含加载器 DLL。
2. 解压模组 ZIP，将其中的 `Mods/ReactiveSuspects` 文件夹复制到**实际正在加载的 UE4SS Mods 目录**。本次测试使用 `ReadyOrNot/Binaries/Win64/Mods`；其他布局请以你的加载器目录和日志为准。
3. 确认存在 `Mods/ReactiveSuspects/Scripts/main.lua` 和 `Mods/ReactiveSuspects/enabled.txt`。如果 `mods.txt` 显式将 `ReactiveSuspects` 设为 `0`，请改为 `1`。
4. 主机启动游戏，日志应显示 `[ReactiveSuspects] READY r12`、`movement=true` 和三个 `SHOT_HOOK_READY`。客机无需安装本模组。

也可在解压后的目录运行安装器，它会先完整备份已有的同名模组：

```powershell
.\Install.ps1 -ModsDirectory 'D:\YourGame\ReadyOrNot\Binaries\Win64\Mods'
```

停用时先关闭游戏，再将 `ReactiveSuspects` 文件夹移出 Mods 目录。不要只删除 `enabled.txt` 却保留 `mods.txt` 中的显式启用条目。

### 行为与参数

以下参数位于 `package/Mods/ReactiveSuspects/Scripts/main.lua` 顶部的 `Config` 中。修改已安装脚本后重启游戏生效。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `ImpactRadiusCm` | `250.0` | 感应半径 2.5 米，包含在旁边约 2 米处开枪 |
| `ShotPathLengthCm` | `10000.0` | 从实际枪口沿射击方向感应，前方最长 100 米 |
| `ReactionSeconds` | `8.0` | 反击持续 8 秒，新攻击事件刷新时限 |
| `TickMs` | `50` | 每 50 毫秒处理一次反应 |
| `EnableMovement` | `true` | 启用原导航侧移、推进和追近 |
| `MoveIntervalSeconds` | `0.9` | 移动请求间隔 |
| `SidestepCm` | `180.0` | 侧移目标距离约 1.8 米 |

感应通道不会被墙面截断，所以隔障碍朝嫌疑人附近开枪也能触发。它是基于真实开火位置和方向的距离判断，并非逐帧测得的实体子弹轨迹。实际子弹能否射穿墙体仍由原版弹道与材质决定。

模组使用武器的真实 `Instigator/Owner` 确认射手，保留服务器权限、敌我关系、存活和逮捕状态检查。不开无限弹药。侧移和追近依赖原版导航，部分位置或动作下移动请求会被拒绝。

### 测试与兼容性

- 39 项 Lua 5.4 离线模拟检查通过，安装包和源码包均逐文件回读校验。
- 本地实测确认未命中触发、隔障碍反击和可见移动。日志包含 `hit=0` 时的 `trigger=shot_direction_near`、移动调用和正常超时结束。[实机结果](evidence/r12-live/diagnosis.md)
- 主机安装、客机表现正常：2026-10-30 玩家反馈确认。没有另行采集客机日志，不将反馈扩大为所有环境的兼容保证。
- 测试加载器为 UE4SS `3.0.1 Beta #0`。测试游戏 EXE 的 SHA-256 为 `ff445331e7144a2dc79ec50c2e6fd42f2a2e7b49ae7b03ae1a6076dcfc769262`。其他游戏或加载器版本需要重新验证；日志中的参数校验失败意味着相关入口未启用。
- 本轮实际捕获了 `Multicast_PerformHitscan` 和 `Multicast_OnFire`。`Server_HitscanHit` 尚未捕获，不将“入口已注册”视为该入口已实机执行。

### 源码与开发

```text
package/Mods/ReactiveSuspects/  可安装 Lua 模组
package/Install.ps1            备份与安装脚本
tools/                        模拟测试、打包和只读分析工具
evidence/                     接口元数据、测试报告与诊断摘要
output/                       可下载模组、源码和校验值
```

运行开发检查和重新打包：

```powershell
python -m pip install -r requirements-dev.txt
python tools/test_mod.py
python tools/build_package.py
python tools/build_source.py
```

测试执行实际 Lua 脚本，使用模拟 UE4SS 接口；离线通过不能代替游戏实测。只读原生分析工具可能需要额外的 Capstone 依赖及你自己的游戏 EXE。仓库不包含游戏资产、UE4SS DLL、原始日志或内存转储。[源码说明](SOURCE-中文.md)

## English

A UE4SS mod for **Ready or Not** that makes suspects retaliate toward the real shooter's position when hit or when a nearby shot direction is detected, even when a door or wall blocks their view. During retaliation, suspects attempt to sidestep, advance, or pursue using the game's navigation.

**Install on the host only.** Missed-shot retaliation and visible movement were tested locally. On 2026-10-30, the player confirmed that client testing worked normally. The multiplayer result is player-reported; see the [multiplayer record](evidence/r12-live/multiplayer-feedback.json).

### Downloads

- [r12 mod ZIP](https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang/raw/refs/heads/main/output/ReactiveSuspects-r12-HostOnly-UE4SS.zip)
- [r12 full source ZIP](https://github.com/AirforceXII/RON-Suspect-Counter-Wallbang/raw/refs/heads/main/output/ReactiveSuspects-r12-Source.zip)
- [SHA-256 checksums](output/SHA256SUMS.txt)
- [Browse the Lua source](package/Mods/ReactiveSuspects/Scripts/main.lua)

### Installation and removal

1. Install a working [UE4SS loader](https://github.com/UE4SS-RE/RE-UE4SS/releases) on the host, then close the game. Loader DLLs are not included in the mod ZIP.
2. Extract the mod ZIP and copy `Mods/ReactiveSuspects` into the **Mods directory used by your active UE4SS installation**. The tested setup uses `ReadyOrNot/Binaries/Win64/Mods`; other loader layouts may differ.
3. Check that `Mods/ReactiveSuspects/Scripts/main.lua` and `Mods/ReactiveSuspects/enabled.txt` exist. If `mods.txt` explicitly sets `ReactiveSuspects` to `0`, change that entry to `1`.
4. Start the game as host. Look for `[ReactiveSuspects] READY r12`, `movement=true`, and three `SHOT_HOOK_READY` entries. Clients do not need this mod.

Alternatively, run the installer from the extracted mod ZIP. It fully backs up an existing copy of this mod before updating it:

```powershell
.\Install.ps1 -ModsDirectory 'D:\YourGame\ReadyOrNot\Binaries\Win64\Mods'
```

To disable the mod, close the game and move the `ReactiveSuspects` folder out of Mods. Removing only `enabled.txt` is insufficient if `mods.txt` still explicitly enables it.

### Behavior and settings

Edit `Config` at the top of `package/Mods/ReactiveSuspects/Scripts/main.lua`. Restart the game after editing the installed script.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ImpactRadiusCm` | `250.0` | 2.5 m sensing radius, including a shot about 2 m beside a suspect |
| `ShotPathLengthCm` | `10000.0` | Forward sensing corridor, up to 100 m from the actual muzzle |
| `ReactionSeconds` | `8.0` | 8-second retaliation window, refreshed by new attack events |
| `TickMs` | `50` | Process reactions every 50 ms |
| `EnableMovement` | `true` | Request native sidesteps, advances, and pursuit |
| `MoveIntervalSeconds` | `0.9` | Interval between movement requests |
| `SidestepCm` | `180.0` | Requested sidestep distance of about 1.8 m |

Walls do not clip the sensing corridor. A shot directed near a suspect behind cover can therefore trigger retaliation. This is proximity sensing based on real firing origin and direction, rather than a frame-by-frame physical bullet track. Actual wall penetration still depends on the game's ballistics and materials.

The mod resolves the real shooter through the weapon's `Instigator/Owner` chain and retains authority, faction, alive, and arrest checks. It does not enable infinite ammunition. Movement depends on native navigation and may be rejected in some locations or activities.

### Testing and compatibility

- All 39 Lua 5.4 offline simulation checks passed. Both archives were read back and compared file by file.
- Local gameplay confirmed missed-shot triggers, retaliation through cover, and visible movement. Logs include `trigger=shot_direction_near` while `hit=0`, movement calls, and normal expiry. [Runtime results](evidence/r12-live/diagnosis.md)
- Host installation with normal client behavior was confirmed by the player on 2026-10-30. No separate client log was collected; this report is not a compatibility guarantee for every setup.
- Tested loader: UE4SS `3.0.1 Beta #0`. Tested game EXE SHA-256: `ff445331e7144a2dc79ec50c2e6fd42f2a2e7b49ae7b03ae1a6076dcfc769262`. Other game or loader versions require verification. A signature-check failure in the log means the affected entry point was not enabled.
- `Multicast_PerformHitscan` and `Multicast_OnFire` were observed during gameplay. `Server_HitscanHit` has not been observed; successful hook registration alone does not prove runtime execution.

### Source and development

```text
package/Mods/ReactiveSuspects/  Installable Lua mod
package/Install.ps1            Backup and installation script
tools/                        Simulation tests, packaging, and read-only analysis
evidence/                     Interface metadata, test reports, diagnosis summaries
output/                       Mod ZIP, source ZIP, and checksums
```

Run the development checks and rebuild the archives:

```powershell
python -m pip install -r requirements-dev.txt
python tools/test_mod.py
python tools/build_package.py
python tools/build_source.py
```

The tests execute the actual Lua script against mocked UE4SS interfaces. Passing them does not replace gameplay testing. Optional native-analysis tools may require Capstone and your own game EXE. Game assets, UE4SS DLLs, raw logs, and memory dumps are not included. The [source walkthrough](SOURCE-中文.md) is currently in Chinese; source comments and tools use English.

