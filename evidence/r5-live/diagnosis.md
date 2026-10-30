# r5实际加载与预检失败

停用BPModLoaderMod后，2026-10-29本地08:42这轮日志出现Loading r5，但未READY：OnRespawnProjectile缺少UnderlyingType，最终DISABLED。此时未安装行为事件钩子，因此无需继续做射击测试。

当前EXE的UHT描述显示UnderlyingType generation_flags=0x0、flags=0x0；这是枚举内部辅助描述，而非运行时函数参数。原提取器没有按CPF_Parm过滤，从而把错误名字同时复制进代码与模拟接口；此前模拟测试未覆盖此类辅助描述。

r6修正提取器：parameters只含CPF_Parm=0x80的描述，其他描述单独保留。实际OnRespawnProjectile参数为RespawnLocation、RespawnRotation、newSpeed、newDamage、projectileReaction。运行时可选探针校验失败只跳过探针，核心行为仍需严格通过自身接口校验。

新回归覆盖：UnderlyingType不是运行时参数；可选诊断参数不匹配仍保留核心命中反击。未据离线回归宣称实机反击已完成。
