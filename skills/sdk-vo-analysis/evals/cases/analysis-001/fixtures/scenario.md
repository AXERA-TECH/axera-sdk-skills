# 客户问题场景

你是 AX615 芯片 FAE。客户报告：ax615 板卡通过 BT656 接口输出 1920x1080@30f 到显示器，程序运行无报错（AX_VO_Init/SetPubAttr/Enable 均返回 0，dmesg 无异常），但显示器完全黑屏无信号。客户提供的信息如下：

1) VO 时序参数（客户代码中 AX_VO_PUB_ATTR_T 的取值）：bIop=1, u16Vact=1080, u16Vbb=36, u16Vfb=4, u16Hact=1920, u16Hbb=148, u16Hfb=88, u16Hpw=44, u16Vpw=5, u32Pclk=74250, bIdv=1, bIhs=1, bIvs=1, bDlbClk=0
2) cat /proc/ax_proc/vo/display_status 输出：device0 enabled=1, chn0 send ok, frame cnt 递增正常
3) 客户说参考了你们的 demo 时序表配置的

请分析问题根因，给出有证据支撑的解决方案。输出需注明每条结论的证据来源。

