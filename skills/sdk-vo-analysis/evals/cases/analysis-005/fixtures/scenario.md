# 客户问题场景

你是 AX615 芯片 FAE。客户报告：

**现象**：ax615 板卡上电后画面整体偏绿，出图正常、无花屏、无撕裂，仅颜色异常；必现。

客户提供的信息：

1) 芯片型号：AX615Q，BT656 接口输出 1920x1080@30 到显示器
2) 视频源：VDEC 解码 H.264 片源，源色域 BT709（客户确认片源为 BT709 高清源）
3) 客户代码片段（CSC 配置）：
   AX_VO_CSC_T stCsc = {0};
   stCsc.enMatrix = AX_VO_CSC_MATRIX_BT601_TO_BT601;  /* 客户以为矩阵随便配一个就行 */
   s32Ret = AX_VO_SetCSC(0, &stCsc);                  /* 返回 0 */
4) 时序参数按已验证表条目 1920x1080@30f_bt656 配置（u32Pclk=148500、bDlbClk=0、bIop=1），
   AX_VO_Init / SetPubAttr / Enable / SendFrame2Disp 均返回 0，dmesg 无异常
5) cat /proc/ax_proc/vo/display_status 关键字段：
   [SDK version]: V3.13.0_20260908...
   ScanType=P Refresh=30 Pclk=148500 InFps=30 OutFps=30 DiscFrames=0 BlkMiss=0
6) 客户怀疑："是不是芯片的 CSC 硬件通路有出厂缺陷？"

请分析问题根因，给出有证据支撑的解决方案。输出需注明每条结论的证据来源。
