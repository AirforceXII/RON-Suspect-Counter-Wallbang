# r1 未反打：实际日志与 r2 修正

2026-10-28用户反馈穿门、穿墙命中都没有反打。此次未启动新的AI采样。

已保留原始UE4SS.log。运行时间戳按日志原样保存，不自行转换为客户端时区。

日志确认UE4SS v3.0.1 Beta #0 / Git d935b5b成功启动，加载Mods/ReactiveSuspects并打印Loading r1；随后出现`DISABLED: function: ...`，没有READY，也没有任何命中、近掠或反击请求记录。因此本轮没有执行本模组反击逻辑，不能据此判定隔墙射击受阻。

对照该版本源代码：UFunction Lua包装类直接继承UObjectBase，其绑定没有UStruct.ForEachProperty；r1的checkSignatures调用fn:ForEachProperty导致初始化失败。UObjectBase已有Reflection():GetProperty，内部将对象转为UStruct再查参数，支持UFunction。

原始来源：

- https://raw.githubusercontent.com/UE4SS-RE/RE-UE4SS/v3.0.1/UE4SS/include/LuaType/LuaUFunction.hpp
- https://raw.githubusercontent.com/UE4SS-RE/RE-UE4SS/v3.0.1/UE4SS/src/LuaType/LuaUFunction.cpp
- https://raw.githubusercontent.com/UE4SS-RE/RE-UE4SS/v3.0.1/UE4SS/include/LuaType/LuaUObject.hpp

r2使用Reflection逐参数检查，并对三个事件、脚本开火/瞄准与导航请求核对关键参数偏移；仍不读写裸内存。初始化异常会记录具体阶段和Lua调用栈。

回归测试改为模拟真实3.0.1的UFunction包装：没有ForEachProperty。共15项离线测试通过；这仍不等于r2已在游戏内执行开火或客机同步通过。
