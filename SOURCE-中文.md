# ReactiveSuspects r12 源码

完整脚本：package/Mods/ReactiveSuspects/Scripts/main.lua，无需编译 DLL 或 PAK。r10 的命中后隔障碍反击已由玩家确认，新增方向触发已在父之罪实机通过，日志命中数为 0；Server_HitscanHit 本轮为 0，尚未实机验证。

1. Config：50 毫秒周期、8 秒反击、250 厘米感应半径、10000 厘米前方感应长度；EnableMovement=true，OverrideCombatTarget=true。
2. onDamage/onNearPass/onImpact：保留命中、原生压制和旧子弹实体撞击入口。
3. onHitscan/onMagazineFire：从 BaseMagazineWeapon 的 Multicast_PerformHitscan 或 Multicast_OnFire 提取真实枪口位置和方向，归一化后生成最长 100 米的感应线段。它不按墙面截断，也不声称实际子弹穿过所有这些位置。
4. onHitscanHit：接收 Server_HitscanHit 报告，用 TraceBegin 到 HitResult.ImpactPoint 的有限路径检测附近嫌疑人。
5. shooterOf：沿武器或弹体的 Instigator/Owner 链取得真实角色，不从玩家列表猜射手。
6. processImpacts：共享有界队列，对点事件计算三维点距，对路径事件计算三维点到有限线段的最近距离。候选上限 128，每秒最多刷新一次；最多排队 64 条，每周期处理 32 条。
7. accept/step/stop：保留 r10 的敌我、权限和存活检查，登记真实目标，使用控制器独立 CombatActivity 请求瞄准与开火。禁止 AddActivity(combat,true)，不把战斗组件装成主活动。r7/r9 的栈溢出证据在 evidence/r9-live/diagnosis.md。r12 只开启已有的 move 路径，约每 0.9 秒请求一次原导航侧移/追近。
8. initialise：校验 UFunction 参数与已知偏移。四个旧行为入口继续保留；三个新武器入口逐一校验、注册并记录结果；两个旧弹体探针仅诊断。
9. InitGameStatePre：从持久 Lua 主状态注册，换图丢弃旧引用；旧版加载器的异步周期只排队，UObject 操作在游戏线程执行。

新增接口来自当前 EXE 的 UHT 元数据，见 evidence/r11-static/shot-interfaces.json；旧 UE4SS_ObjectDump 只用于发现名字，没有照用旧原始偏移。反射的偏移检查在运行时执行，不直接读写游戏内存。

tools/test_mod.py 使用 lupa2.6 / Lua5.4 执行真实脚本与模拟接口，共 39 项检查。覆盖未命中路径触发、方向归一化、射程和三维距离、有限命中报告路径、客户端/未知射手/敌我/换图排除、有界队列，以及旧开火链与活动层级。r11 实机已证实 Multicast_PerformHitscan 和 Multicast_OnFire 被调用，并在 hit=0 时触发反击。Server_HitscanHit 本轮为 0。r12 已由玩家确认反击并有移动；保存日志中 29 次方向触发、277 次移动请求、168 次被导航拒绝，25 次超时结束。2026-10-30 玩家反馈客机测试正常；此项为玩家联机反馈，见 evidence/r12-live/multiplayer-feedback.json。原始本地日志摘要见 evidence/r12-live/verification.json。

tools/inspect_interfaces.py 只读当前 EXE 元数据。tools/build_package.py 和 build_source.py 打包并逐文件回读。复现顺序：tools/test_mod.py、tools/build_package.py、tools/build_source.py。开发依赖见 requirements-dev.txt，tools/runtime 不进入源码包。

tools/Capture-Hang.ps1 是单次只读线程转储工具，仅申请 QUERY_INFORMATION|VM_READ；不注入、不写进程、不调用游戏函数。本轮没有启动线程采样。原始日志、崩溃报告、转储和游戏二进制不放入分发 ZIP。




