# 根因收敛决策树与证据分级（Phase 5）

把前四阶段的证据汇总，做最终判定，并**诚实标注证据强度**。

## 一、决策树

```
Q1. 日志里有 ax_cmm_free failed! Block not found（或 BlockId invalid / giveback fail）吗？
├─ 无 → 大概率不是本路径；若现象仍疑似内存，回 Phase 2 补日志，或考虑其它诊断路径。
└─ 有 → 记下 phyaddr，继续。

Q2. 用 proc/API 把该 phyaddr 反查 owner，owner 是不是释放它的那一方？
├─ owner ≠ 释放方（如 owner=IVPS/pool，释放方=应用） → 跨所有权释放。到 Q3。
├─ owner = 释放方本人 → 看是否重复释放 / 释放后未清指针（stale）。到 Q3。
└─ 查不到 owner（token 缺失/已 dump 不到） → 靠 Q3 的代码配对审查补证。

Q3. 调用序列里是否违反三对配对铁律？
├─ 是（取帧后又 MemFree / 对 Mmap 地址 MemFree / 同块 free 两次 / A取B放） 
│     → 根因成立：错误使用 AX_SYS_MemFree，释放了不属于自己/已释放的 CMM 内存。
└─ 否 → 本路径不成立，转其它诊断路径或继续收集证据。

Q4. 去掉那次多余/错误的释放后，还复现吗？
├─ 不再复现（挂测足够时长） → 根因闭环（强证据）。
└─ 仍复现 → 根因判断有误或还有第二个问题，回 Phase 1 重新分诊。
```

## 二、证据强度分级

下结论时按这个标准分级，避免把"推断"说成"事实"：

| 级别 | 成立条件 | 措辞 |
|---|---|---|
| **强（已证实）** | 日志有 `Block not found` + owner 反查到跨所有权 + 代码确有配对违反 + 去掉后不复现，形成闭环 | "根因是 …，已闭环验证" |
| **中（推断）** | 有非法释放证据，但"误释放他人内存 → 踩内存 → 硬挂"的**逐拍时序未直接抓到**（硬挂常无 backtrace），主要靠"改后不复现"支撑 | "最可能通过 … 机制挂死，为合理推断" |
| **弱（存疑）** | 仅现象相似，缺日志/owner/代码任一环 | "疑似 …，需补充 … 才能确认" |

**关键提醒**：`Block not found` 证明的是"发生过非法/重复 free"（强）；"它就是通过误释放他人内存这条路径挂死"通常是**中等证据的推断**。两者要分开说。

## 三、结论输出模板

```
## 结论（根因 + 证据强度）
一句话根因 + 强/中/弱。

## 证据链
现象(退出阶段/硬挂) → 日志关键字(phyaddr=0x..) → owner 反查(token=..，非释放方) → 配对违反(取帧后又 MemFree)

## 修复建议
具体到怎么改调用序列（通常：删掉多余的 AX_SYS_MemFree，保留 Get/Release 与 Mmap/Munmap 配对）。

## 预防
token 规范、释放即清零、封装配对、code review 规则（详见 fix-and-prevention.md）。

## 仍需确认的点（若未闭环）
还需要哪些日志/复现数据来把证据从"中"提到"强"。
```

## 四、如果要把证据从"中"提到"强"

- 在 `AX_SYS_MemAlloc/MemFree` 外包一层，打印 `phyaddr + size + token + pid + 调用栈`，追踪**同一个 phyaddr 的完整生命周期**，抓"成功 free → 重分配 → 再 free"的 ABA 时序。
- 对被踩地址下 GDB 硬件 watchpoint，抓第二次非法写/释放的栈。
- **挂死 / NMI 不响应 / backtrace 被截断时**：开 ramoops/pstore（`CONFIG_PSTORE=y`），崩溃后热重启（复位、勿断电）读 `/sys/fs/pstore/console-ramoops-0`、`dmesg-ramoops-0` 拿崩溃前完整栈；串口还在但敲不进时先 `echo 7 > /proc/sys/kernel/printk`、`echo 0 > /sys/module/printk/parameters/console_suspend`。详见 `log-capture-guide.md`。
- ramoops 也抓不到、软件手段用尽时才上 JTAG（标杆案例排查早期客户即曾因硬挂无栈而考虑上 JTAG）。
