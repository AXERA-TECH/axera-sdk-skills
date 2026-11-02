# AX615 DDR 自助排查 Skill

本目录提供面向 AX615 SDK/BSP 的 DDR 问题自助排查流程。内容聚焦于公开可复核的源码导航、启动日志判读、配置核对、training/BIST 测试流程和问题交接，不替代芯片手册、颗粒数据手册或原厂支持。

## 自动化脚本与评测
- **排查工具化**：提供宿主机端日志扫描脚本，自动抽取关键配置锚点，减少人工捞取日志的疏漏。
- **评测标准化**：内置基于历史真实客诉的 EVAL 测试集，用于回归测试和量化评估诊断准召率。

## 用途

适用于以下现象的初步定位：

- DDR 初始化失败、training 失败或超时；
- BIST/memtest 失败、读写错误或数据校验错误；
- 启动不稳定、偶发死机或运行时内存错误；
- 频率、温度、电压或板卡变化后出现的稳定性差异；
- DDR 类型、位宽、Rank、频率和配置分支核对。

## 内容边界

- 本目录只保留诊断方法、源码入口和证据模板。
- 不分发芯片级内部资料、原始地址清单、位域清单或 PHY 物理实现细节。
- 需要受控资料确认的结论，只记录为“待原厂确认”，不在公开文档中复述受控内容。
- 不建议未经规格依据和回归验证的参数修改，也不直接修改 DDR 驱动源码。

## 指定源码入口

```text
/boot/bl1/driver/ddr/ax615_ddr
```

常用入口：

- `ddr_init.c`：初始化入口、协议 flow、频率选择、training/BIST 调度；
- `ddrmc_train_flow_no_lp.c`：部分 DDR training 流程和阶段日志；
- `ddr/`：公共配置、协议 timing 和源码接口定义。

## 使用方式

提取锚点（可选）：在 PC/编译服务器上运行 sh scripts/scan_ddr_log.sh <串口日志文件>，提取环境锚点与初判结论。

在支持 skill 的环境中显式调用：

```text
/sdk-bsp-ddr-diag-skill
```

排查时先确认实际镜像、源码版本、板卡和颗粒信息，再按 `SKILL.md` 的 S0～S5 流程逐步收集证据。

## 文档索引

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 主流程、边界和输出模板 |
| `reference/FAQ.md` | 常见现象、低风险验证和适用边界 |
| `reference/code_map.md` | 源码入口、调用链和可搜索特征 |
| `reference/platform_version_diff.md` | 型号、协议、频率和配置分支差异 |
| `reference/known_suspects.md` | 尚未闭环的源码可疑点 |
| `reference/handoff_template.md` | 原厂交接文档模板 |
| `reference/eval_contract.md` | 评测场景的结构化输出契约 |
