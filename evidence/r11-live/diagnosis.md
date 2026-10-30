# r11 主菜单加载

2026-10-29 本轮实时日志确认 Loading r11，三个新增 BaseMagazineWeapon 入口均出现 SHOT_HOOK_READY，随后 READY r11。参数和已知偏移检查通过，持续 STATUS 更新。

当前处于主菜单，新增射击计数为 0 属于预期。注册成功不能证明射击事件已实际触发，也不能证明未命中时已经反击；等待玩家进入关卡测试。

## 父之罪未命中实测

玩家确认“未命中也会反击”。保存的 UE4SS.near-shot-test.log 中，本轮 hit=0、near=0、raw_impacts=0，而出现三个 START trigger=shot_direction_near，分别指向真实 BasePlayer。首轮反击后 fire_requests=13，随后 STOP reason=expired，后续周期继续。

实际被调用的新增入口是 Multicast_PerformHitscan 和 Multicast_OnFire；Server_HitscanHit 本轮为 0，不能宣称该命中报告入口已实机验证。raw_hitscans=47、raw_fires=48 包含嫌疑人还击产生的射击；shot_near 是几何匹配计数，也包含随后被权限/敌我/自我过滤拒绝的候选，不等于接受反击次数。三个 START 才是接受记录。

本轮没有 ReactiveSuspects 错误日志。主动移动仍为关闭，原版客机同步未测试。下一版只恢复原导航移动请求，r11 保存为当前可回退基准。
