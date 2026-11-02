# 客户问题场景

你是 AX615 芯片 FAE。客户报告：AX615Q 板卡 BT656 输出 1920x1080@30f，画面偶发撕裂。送帧线程约 60fps，s32MS=0；帧来自 AX_POOL_GetBlock，但 send 返回后立即覆写同一 block；AX_VO_QueryChnStatus 和 AX_VO_EnumMode 返回 0x80038A14；proc 中 InFifoSize 长期等于 FifoLen，DiscFrames 持续增长。请给出根因与修正方案。

