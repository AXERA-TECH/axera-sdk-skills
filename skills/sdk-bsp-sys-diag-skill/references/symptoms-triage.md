# 现象分诊：识别特征与问题清单（Phase 1）

目的：快速判断"这个挂死/异常"是否属于 **CMM 内存错误释放** 这一类，从而决定是否沿本路径深入。

## 一、识别特征（命中越多越像"错误释放 CMM"）

| 维度 | 高度可疑的特征 |
|---|---|
| 触发阶段 | 挂在**退出 / Stop / 关流 / DeInit / Destroy / 切分辨率**时，而不是稳定运行时 |
| 硬度 | CPU **硬挂**、无响应，甚至 **NMI 都不响应** → 典型的内存/总线被踩，而非普通死锁或 D 状态 |
| 复现 | 概率较高、与**退出时序 / 多线程退出顺序**强相关 |
| 日志关键字 | `ax_cmm_free failed! Block not found,phyaddr=0x...`；`[Pool] ... BlockId :0x.. invalid`；`giveback_to_pool ... virt get fail`；`X blocks are not free, CMM<..> should not be unregistered` |
| 调用模式 | 应用在 `Get*Frame + Release*Frame` 之后**又调了 `AX_SYS_MemFree`**；或对 `AX_SYS_Mmap` 返回的地址 `MemFree`；或同一 buffer 释放两次；或"A 模块取、B 模块放" |

> 口诀：**退出阶段 + 硬挂 + `ax_cmm_free ... Block not found` ≈ 先查谁在乱调 `AX_SYS_MemFree`。**

## 二、分诊问题清单（按需挑问，别一次全抛）

**现象与时机**
1. 挂死/异常具体发生在什么时候？运行中稳定出现，还是**退出/关流/切换**时出现？
2. 挂的时候系统还有反应吗？能敲串口吗？（完全无响应/NMI 不响应 → 硬挂）

**复现**
3. 复现概率多高？有没有稳定的复现步骤或时序？
4. 单路还是多路、多线程？退出时各线程/模块的关闭顺序是怎样的？

**涉及模块与调用序列**
5. 出问题的数据流经过哪些模块？（VIN / IVPS / VENC / VDEC / NPU …）
6. 贴一下你**从取数据到释放**的完整调用序列，务必包含所有 `AX_SYS_MemAlloc/MemFree/Mmap/Munmap` 和 `Get*Frame/Release*Frame`。
7. 这块内存/这帧**是你自己 `AX_SYS_MemAlloc` 申请的吗**？`MemAlloc` 的 token 填的什么？（答不上来 → 很可能在释放别人的内存）

**环境**
8. 芯片型号 + SDK/BSP 版本？
9. 有没有串口 log / `/opt/data/AXSyslog/` 下的日志（`axdmesg`）/ 复现前的 `mem_cmm_info` 快照？系统是否开了 ramoops(pstore)？有没有 Jira 工单？

## 三、分诊结论怎么下

- **命中 ≥3 条特征（尤其含"退出阶段"+"硬挂"+某条 CMM 日志关键字）**：判为"高度疑似 CMM 错误释放"，进入 Phase 2/3/4 深入。
- **命中内存不足特征（起流报 0x...18、提示 CMM isn't enough、mempool FreeCnt=0）**：直接走 **`references/nomem-diagnosis.md`**，做内存不足快速定界，不硬套 MemFree 错误释放。
- **只命中 1–2 条**：先进 Phase 2 抓/看日志再判；在报告里注明"尚不能排除其它方向"。
- **完全不命中内存特征**（例如纯业务超时、纯功能不对）：说明本技能可能不适用，建议按常规方向排查，或等待框架补充对应诊断路径（见 SKILL.md 的"内置诊断路径目录"）。
