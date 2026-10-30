# ReactiveSuspects r12：恢复移动反击

r11 已在父之罪确认未命中也会反击。r12 只开启原导航移动请求，保留 r11 的触发、真实射手登记和原版武器开火链。r12 已由玩家确认反击并有移动，日志也记录到方向触发、原导航请求和正常超时退出。

## 行为

- 被命中、原生近弹压制或已收到的附近弹着点可触发。
- 实际开火方向：从枪口沿前方最多 100 米、距离该有限线段 2.5 米内的嫌疑人触发。感应不按墙面截断，也会覆盖同一方向上位于障碍后的嫌疑人；它不是逐帧子弹轨迹。
- 射线命中报告：使用 TraceBegin 至 ImpactPoint 的有限线段；该报告入口尚未实机捕获。
- 每次反击持续 8 秒，新事件刷新时限。
- 约每 0.9 秒请求一次侧移或推进。连续受阻时尝试沿原导航追近，远于 10 米优先追近。侧移目标约 1.8 米，实际能否移动取决于原导航和当前动作。
- 结束时只清理自己的开火与仍归本次请求所有的移动，不替换主活动，不给无限弹药。

## 安装

关闭游戏后，将 Mods/ReactiveSuspects 复制到实际 UE4SS Mods 目录，或运行 Install.ps1 -ModsDirectory 指定目录。安装器完整备份旧模组，只更新本模组。本机目录：

F:\SteamLibrary\steamapps\common\Ready Or Not\ReadyOrNot\Binaries\Win64\Mods

enabled.txt 启用本模组；mods.txt 如显式停用 ReactiveSuspects，需要解除该条停用。关闭游戏后移除 enabled.txt 可停用本机没有显式启用条目的模组。

包不包含 UE4SS DLL，不改 PAK。本机对象缓存关闭和 BPModLoaderMod 临时停用的隔离配置保持原样，原配置有备份，其他环境不应照搬。退回已验证基准可安装 ReactiveSuspects-r11-HostOnly-UE4SS.zip。

## 测试

日志应出现 READY r12、movement=true 及三个 SHOT_HOOK_READY。进入单机关卡，向嫌疑人旁约 2 米处打一发，先不要命中。观察是否隔障碍反击、是否尝试侧移或推进，以及停止触发 8 秒后能否正常退出。

日志 START trigger=shot_direction_near 表示接受方向触发；raw_hitscans/raw_fires 是真实武器事件，shot_near 是几何匹配候选，不等于接受次数。fire_requests/move_requests 只代表原生请求已提交，实际动作仍需观察。rejected_moves 表示导航请求被直接拒绝，STOP reason=expired 表示本次模组反击结束。

50 毫秒周期，路径队列最多 64 条，每周期处理最多 32 条，嫌疑人候选最多 128。39 项离线检查通过。r11 的未命中反击已实机确认；r12 主动移动已实机确认，2026-10-30 玩家已反馈客机测试正常，联机结论来自玩家反馈。部分移动请求被原导航拒绝，不能保证每次都能移动。穿透取决于原版弹道。



