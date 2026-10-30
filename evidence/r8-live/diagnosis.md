# r8 卡死与线程快照（2026-10-29）

用户确认再次卡死且保留进程。UE4SS.hang.log实际地图为RoN_Tower；READY r8确认movement=false。命中后ScriptedLookAtActor、ScriptedFireAtActor均返回，随后STEP_END与REACTION_TICK_END均出现，未出现REACTION_TICK_RESUMED。没有主动导航请求。

进程26616于09:33:42、09:34:07分别生成MiniDumpNormal快照，仅申请QUERY_INFORMATION|VM_READ，没有目标进程写入或注入。239个线程；两份快照中线程41304均执行游戏原生代码，指令位置分别为EXE+4bb3cf4、EXE+4e78325。

使用当前EXE的.pdata展开游戏模块帧，两份快照均经过4ce0b30→4ce6810→4cf6240→4b2a962这组函数。该展开工具只支持有界的常规x64展开，离开游戏模块后停止；原始栈扫描结果只是地址候选，不能单独当作调用栈。相关证据为两个.unwind.json、hang-native-functions.json、hang-dispatch.json和原始.dmp。转储仅留在本地，不放入分发包。

静态核对：ScriptedFireAtActor的实现将bOverrideTarget保存于战斗活动+0x24c；4cf6240读取此位，开启时调用4ce6810的目标参数为null。r8脚本明确传true；快照经过相应调用返回点4cf6330。这支持优先隔离强制覆盖分支，但尚不能证明它是唯一根因。不能声称线程快照已证明修复。

r9只将OverrideCombatTarget=false，保留r8的目标登记、活动切换、瞄准、开火时长和关闭主动移动状态。实际稳定性与反击仍待验证，不能承诺此隔离设置已实现无视视线反击。

格式参考：Microsoft MINIDUMP_THREAD、MINIDUMP_MODULE以及x64 exception handling文档。UE4SS源码d935b5b仅作调度核对；本次快照主要游戏帧没有落在Lua调用内部，不据此认定或排除加载器的间接影响。
