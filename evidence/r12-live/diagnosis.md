# r12 未命中与移动反击实测

2026-10-29 玩家反馈“反击并有移动”。本轮 READY r12、movement=true，游戏目录脚本与源码逐字节相同。

首次反击附近的 STATUS 为 hit=0、starts=1、fire_requests=10、move_requests=7；START 原因为 shot_direction_near。这项触发不依赖命中嫌疑人。全日志共 29 条 START，均为方向触发；目标包括实际玩家和开火的 SWAT 队员。

本轮共提交 277 次移动请求，168 次被原导航直接拒绝。29 个反击实例的首次 RequestMoveAsync 均有 CALL_END；这只是调用返回，实际移动由玩家观察确认，不能把请求数当成移动距离或成功次数。移动受原版导航和当前动作约束。

记录到 25 次 STOP reason=expired，以及失效/不再活跃对象的结束记录。最后 STATUS active=0，后续日志仍更新。保存日志未发现 ReactiveSuspects 错误。此结论限于本次测试，不代表所有地图和所有动作均通过。

日志对象路径涉及 RoN_Sins、RoN_Island、RoN_Tower；路径出现只说明本轮日志涉及这些场景，不能单独视为各地图完整验收。Server_HitscanHit 计数仍为 0，实际新增触发来自 Multicast_PerformHitscan、Multicast_OnFire。

结论：r12 的未命中反击和可见移动由实机反馈与日志共同确认。保持此版，不再修改运行脚本。后续于 2026-10-30 玩家反馈客机测试正常，联机记录见 multiplayer-feedback.json；本段本地日志本身不包含客机采样。结构化结果见 verification.json，原始日志仅保存在本机。

