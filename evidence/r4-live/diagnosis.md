# r4 实际测试

2026-10-29，玩家回报仍没有反击。已保存 UE4SS.first-combat.log；安装脚本SHA256与r4源码一致：3bdeac0429ab2ca793d410d5a81c8c9e6a997575e9153e01eda00a4701838d92。

实际日志：READY r4；GameState initializing；hit=3，但在main.lua:110的targeting:GetClass()处出现“attempt to call a UObject value”，starts/fire_requests/move_requests均为0。near、impacts、impact_near也为0。impacts当时在类型/权限过滤后计数，无法据此判断入口是否被调用。

最初把GetClass错误归因于版本缺少接口，这个判断已纠正：[对应d935b5b源码](https://github.com/UE4SS-RE/RE-UE4SS/blob/d935b5b/UE4SS/include/LuaType/LuaUObject.hpp#L390)确实注册GetClass，随包默认模组也使用它；本地DLL包含GetClass、CallFunction符号字符串。因此不能宣称这是版本没有此方法；真实接收对象/包装状态尚待记录。

r5将诊断置于pcall内，不再以GetClass诊断成功作为执行条件。使用角色上已经可用的IsA绑定核对组件和活动类别，再直接调用经元数据验证的UFunction。新增过滤前raw_impacts、raw_near，以及只记录、不当作弹着点的BulletProjectile重生/验证事件探针。样本日志数量有界。

对应源码支持显式UFunction(receiver,...)：[call_ufunction_from_lua](https://github.com/UE4SS-RE/RE-UE4SS/blob/d935b5b/UE4SS/src/LuaType/LuaUObject.cpp#L64)。接收对象仍须通过真实IsA核对；离线模拟不证明原版AI实际执行。
