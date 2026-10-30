# r2 启动闪退与 r3 修订依据

2026-10-28，当前游戏 EXE SHA256：FF445331E7144A2DC79EC50C2E6FD42F2A2E7B49AE7B03AE1A6076DCFC769262。UE4SS 为 3.0.1 Beta #0 / d935b5b。

## 实际对照

| 条件 | 玩家确认的结果 | 日志 |
|---|---|---|
| 原对象缓存开启，r2 启用 | 启动闪退 | 本目录 UE4SS.log，23:35:34 本地时间最后写入；三个 native hook 注册且 READY r2 后退出 |
| 原对象缓存开启，移走 r2 | 仍然闪退 | ../ue4ss-without-reactive/UE4SS.log，23:38:15；未加载 ReactiveSuspects |
| 临时停用 dwmapi.dll，UE4SS 不加载 | 可以正常进入主菜单 | 玩家回报；引导 DLL 完整保留，未更改游戏 EXE |
| 恢复 UE4SS，仅 bUseUObjectArrayCache=false，r2 停用 | 可以进入主菜单并保持约30秒 | ../ue4ss-without-reactive/UE4SS.cache-off.log，23:42:21；原默认模组保持 |
| 缓存仍关闭，恢复相同散列的 r2 | 再次闪退 | ../r2-cache-off-crash/UE4SS.log，23:44:00；仍在 READY r2 后退出 |

日志行使用 UTC，表格“最后写入”使用 Windows 本地时间 UTC+8。Saved/Crashes 中最新已存在的 UE 报告写入于23:06，早于本轮，不当作 r2 的崩溃栈。未取得可归因于本轮的 native 异常调用栈。

结论：关闭对象缓存后基础 UE4SS 的一次启动对照通过，但相同条件下 r2 仍单独触发启动故障。不能把缓存调整当作 r2 已修好，也不能将 READY 当作游戏稳定或 AI 已执行。

## r3 的源码依据

[UE4SS 3.0.1 LuaMod.cpp](https://github.com/UE4SS-RE/RE-UE4SS/blob/v3.0.1/UE4SS/src/Mod/LuaMod.cpp)：

- 1780–1802：RegisterLoadMapPreHook 保存调用时的 Lua 状态。r2 在 ExecuteInGameThread 的临时回调内注册。
- 2669–2696：ExecuteInGameThread 的任务执行后解除该临时 Lua 线程的 registry 引用，允许 GC。长期回调继续依赖这个状态不合适。
- 3298–3305：LoadMapPre 向 Lua 栈推入 Engine、World、URL、PendingGame、Error 五个参数，但使用四参数调用；World 和 PendingGame 的间接指针形式也与 Post 路径不同。
- 3333–3341：LoadMapPost 使用五参数调用。本机随包 BPModLoaderMod 在主脚本中使用这个 Post API，基础环境对照已能进入主菜单。

r3 将换图清理改为主脚本入口注册 RegisterLoadMapPostHook，只清空 Lua 状态而不调用旧地图角色；三个命中/近掠事件、反击和移动设置保持。对象缓存保留为 false，原配置备份位于 UE4SS 根目录 ReactiveSuspects-backups。

这是有源码依据的兼容修订，不是已有 native 栈确认的唯一崩溃原因。r3 的实际启动、进关卡和战斗需要分别记录；离线测试模拟了注册阶段，不能复现旧加载器的 C++ 崩溃或证明其已消失。

## r3实际结果与r4继续修订

r3实测已进入主菜单，日志持续STATUS；进入关卡后hit计数达到10，但AddKnownEnemy成员调用报“attempt to call a UObject value”，所以fire_requests和move_requests为0。原版近掠near计数仍为0，不能认为这一入口覆盖了实际测试。

r4新增当前EXE的Projectile.Multicast_SpawnImpactEffects(Hit,EffectsClass,DecalScale,bExitImpact,bArmorImpact)，按2.5米三维距离选择嫌疑人，保留真实弹丸射手归属。目标登记改用UE4SS显式CallFunction，调用前验证TargetingComponent真实类别。

进一步检查3.0.1 LuaMod.cpp第3357行：LoadMapPost在第一个订阅者执行后就return，通常首先注册的BPModLoaderMod会使后续订阅者收不到回调。r4改在持久主脚本注册InitGameStatePre；该API遍历全部订阅者，清理时不调用旧角色。

22项离线模拟检查不等同于原生UE4SS行为；r4仍需实际加载、弹着点触发和原版客机验证。
