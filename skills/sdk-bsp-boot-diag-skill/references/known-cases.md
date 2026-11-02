# AX615 启动匿名案例

以下案例只保留可公开复用的技术特征。案例标签不是工单号，不能替代当前设备的日志、版本和 A/B 证据。

## 使用规则

- 同时匹配芯片/介质、版本关系、首个异常和复现条件后，才能引用案例方向。
- 历史案例已关闭不代表当前问题具有相同根因。
- 当前源码只代表用户提供的工作区，必须核对实际运行镜像的构建来源。

## BOOT-CASE-A：无线干扰相关的概率性乱码重启

- **现象**：开启无线功能后概率性串口乱码、死机并由 watchdog 重启；有线网络对照不复现，屏蔽或改变天线距离后复现率变化。
- **判断边界**：只有天线距离/屏蔽状态形成稳定 A/B 差异，复位原因与时钟波形也支持干扰方向时，才列为高可信候选。
- **验证**：保持软件、供电和温度不变，记录天线远近、有无屏蔽的复现率、reset reason 和 24 MHz 波形。晶体驱动调整只能作为受控验证，不能作为通用修复值。

## BOOT-CASE-B：DDR2 reboot 后 training fail

- **现象**：DDR2 设备在 watchdog reboot 后进入 `write deskew training fail!`、`write eye training fail!`，冷启动与 reboot 表现不同。
- **已知方向**：历史修复涉及 DDR reset 时序、PHY timing 和 auto self refresh。日志、平台和复位方式全部匹配时，只能判为已知修复候选。
- **验证**：核对 BL1 commit 和 `drf_auto_self_ref_en` 等代码特征；同一板卡分别统计冷启动和 watchdog reboot。详细 training 分析交给 DDR 诊断 skill。

## BOOT-CASE-C：SPL/U-Boot 共享结构 ABI 不兼容

- **现象**：只升级 SPL 或 U-Boot 后启动失败，改用成套镜像恢复；两个阶段共享 IRAM 数据结构。
- **机制候选**：结构字段顺序、大小或对齐变化会让后级按错误偏移解析前级数据。
- **验证**：记录两侧构建版本，比较共享结构的字段顺序、`sizeof`、offset 和头文件来源，再用成套镜像验证。没有结构差异或成套镜像仍失败时，应推翻该方向。

## BOOT-CASE-D：SPI NAND rootfs 读取/ECC 异常

- **现象**：掉电后 rootfs 偶发加载失败，日志包含 `spinand_check_ecc_status: status = 0x30` 和 page read error，重新写入镜像后恢复。
- **代码边界**：`spinand_check_ecc_status()` 优先调用器件专用 `eccinfo.get_status`；缺少专用实现时才使用通用掩码。不能脱离 NAND 型号固定解释 `0x30`。
- **验证**：提供 NAND 料号、对应驱动、异常块 data/OOB、坏块/ECC 统计和掉电时写入轨迹；做只读/可写、原频/降频、受控掉电的单变量 A/B。只读样本暂未复现不足以证明根因。
