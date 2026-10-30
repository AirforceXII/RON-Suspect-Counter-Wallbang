# r9 栈溢出与 r10 修订依据（2026-10-29）

用户反馈卡死并保留进程。核对时活动游戏已经退出，只有旧的零线程进程条目和09:47:26创建的CrashReporter。本轮不是成功取得现场线程快照，而是读取了游戏自行生成的崩溃报告，原件保存在crash-original。

报告错误为EXCEPTION_STACK_OVERFLOW（0xc00000fd）。PCallStack共99行，其中返回点EXE+4ce0b01重复97次。此前r7的09:17:16报告也是栈溢出。摘要见crash-summary.json。没有根据旧报告日期推定本轮原因。

当前EXE SHA256为ff445331e7144a2dc79ec50c2e6fd42f2a2e7b49ae7b03ae1a6076dcfc769262。静态核对：

- 4ce0b01位于函数4ce0a90，对控制器获取的当前活动调用虚表+0x340后返回。
- 该函数经4a87e90取控制器+0x888的活动。
- GetCombatActivity的当前原生入口4803930从控制器+0x9a0返回另一个活动槽。
- r7/r9脚本调用AddActivity(combat,true)，随后日志COMBAT_ACTIVE来自CurrentActivity与GetCombatActivity地址相等的实际判断。

重复原生调用栈、不同的活动槽及日志中的对象相等判断共同指向：把内部战斗组件安装成当前主活动，使原生检查委派回自身。r9关闭bOverrideTarget不足以改变这个错误的活动层级。

崩溃转储没有包含相关控制器/战斗对象的堆页，因此没有声称已从堆中直接回读这两个指针。根因解释依据是调用栈、当前EXE代码与运行日志的组合。

r10移除AddActivity(combat,true)及等待combat成为CurrentActivity的错误条件，沿用控制器独立战斗槽发出瞄准/射击请求。若发现旧的自委派关系则停止本次请求；不写偏移、不改原生代码。恢复bOverrideTarget=true，主动移动仍关闭，先验证稳定性与实际反击。离线检查增加/改写主活动保持不变和拒绝自委派的回归；实机修复、无视视线反击和客机可见性仍待测试。
