# r10 实机基准

玩家于 2026-10-29 确认隔障碍反击成功，但仍需直接命中嫌疑人，近弹触发未达到要求。

保存的 UE4SS.successful-hit.log 包含 READY r10、START trigger=bullet_hit、后续状态更新和正常过期。截取时最后 STATUS 为 hit=73、near=1、raw_near=2、raw_impacts=0、respawns=0、validations=0、starts=28、fire_requests=279、move_requests=0。计数包括多个关卡；fire_requests 不是实际命中或实际开枪计数。

这证明原生近弹/压制入口并非完全未调用，但远少于命中，且 Projectile 的三个入口均未捕获事件。不能继续仅提高撞击感应半径，因为没有输入事件。

r11 因此增加 BaseMagazineWeapon 的射击和射线报告入口；保留本轮已成功的目标登记、瞄准与开火链。新入口尚未实机验证。
