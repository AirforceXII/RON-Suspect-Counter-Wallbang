# r7 实机卡死记录（2026-10-29）

用户反馈：再次卡死或严重卡顿。UE4SS.hang.log中的地图路径是RoN_Tower，并非父之罪。

最后一次命中后，AddActivity返回true；随后记录COMBAT_ACTIVE。GetEquippedWeapon、ScriptedLookAtActor、ScriptedFireAtActor、GetPawnLocation、GetAttackerLocation、RequestMoveAsync均记录CALL_END。

这些记录证明调用已经返回，不能证明实际射击或移动成功，也不能把故障认定为某个调用未返回。首轮之后没有新的STATUS。

尝试只读线程快照时，未找到仍有线程的游戏进程，故未产生转储。没有卡死线程栈证据。

r7已完整备份并移除enabled.txt，记录见disabled.json。r8只新增EnableMovement=false隔离和处理周期结束/恢复标记；目标登记、活动切换、瞄准与开火参数不变。尚未证明修复卡死。

后续r9调查时，在游戏Saved/Crashes中找到与r7日志时间09:17:16对应的崩溃报告，错误为EXCEPTION_STACK_OVERFLOW。此前单次现场采集未获得转储，不代表游戏没有自行生成报告。r10修订依据见../r9-live/diagnosis.md。
