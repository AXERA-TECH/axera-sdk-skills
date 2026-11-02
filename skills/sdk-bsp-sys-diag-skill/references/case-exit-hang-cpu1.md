# 标杆案例：音视频退出时 CPU1 挂死（ISSUE-CASE01）

这是本技能第一条诊断路径的金标准案例。它展示了"现象 → 日志 → owner 反查 → 配对审查 → 收敛 + 证据分级"的完整推理，可作为处理同类问题的范例。

## 背景

- 工单引用：`https://jira.example.com/browse/ISSUE-CASE01`（音视频退出的时候 CPU1 挂掉）
- 现象：音视频**退出**时 CPU1 挂死，挂后无任何响应，**NMI 中断都无法响应**，复现概率高。客户希望用 JTAG 协助。
- 客户评论给出的调用序列：
  ```
  AX_IVPS_GetChnFrame
  AX_SYS_Mmap
  AX_SYS_Munmap
  AX_IVPS_ReleaseChnFrame
  AX_SYS_MemFree   ← 多余
  ```
  客户自查：多调用了 `AX_SYS_MemFree`，删除后挂测一周未再复现。

## Phase 1 分诊：命中多条特征

退出阶段（✓）+ 硬挂 NMI 不响应（✓）+ 复现率高（✓）+ 可疑调用序列（✓）→ 高度疑似"CMM 错误释放"。

## Phase 2 日志：抓到非法释放

关键行（`ax_syslog_0211.txt`）：
```
[C1][SYS][E][353] [CMM][Error]:ax_cmm_free failed!Block not found,phyaddr=0x46208200.
```
它夹在退出流程里：
```
[C1][IVPS] ivps_sched_chn_disable ... enter grp0 chn0
[C1][BASE] ax_base_sync_agent_session_deinit ... session 1 deinit
[C1][SYS]  ax_cmm_free failed! Block not found, phyaddr=0x46208200   ← 非法释放
[C1][VENC_DRV] VENC_CAL_StopRecvPic ...
```
另有 `[Pool] BlockId :0x0 invalid`、`giveback_to_pool ... virt get fail u32BlkId 0x5e00d000` 等失效句柄报错，佐证退出期对象生命周期出问题。**锚点 phyaddr = 0x46208200。**

## Phase 3 owner 反查：这块不归应用管

`phyaddr=0x46208200` 落在 `cmmpool=anonymous,0,0x43200000,78M` 这个 CMM 分区内；它是 IVPS 帧（pool block，带 `u32BlkId`）的底层内存，owner 不是应用自己 `MemAlloc` 的。应用却对它 `MemFree` → 跨所有权释放。

## Phase 4 配对审查：违反铁律

对着代码看三对配对（`msp/component/...`）：
- `AX_IVPS_GetChnFrame → ivps_osal_frame_get`，帧带 `u32BlkId`；`AX_IVPS_ReleaseChnFrame → ivps_osal_frame_release` 已按 `u32BlkId` 完整归还 → 帧的所有权本就归 IVPS pool。
- `AX_SYS_MemFree → ioctl_mem_cmm_free`，只应释放自己 `AX_SYS_MemAlloc`（`→ ioctl_mem_cmm_alloc`）的内存。
- 全仓 40+ 处取帧调用，之后跟的都是 `ReleaseChnFrame`，**无一跟 `MemFree`**；唯一用 `MemFree` 的 QSDemo，释放的是它自己 `MemAlloc("QR_CODE_BUFF")` 的 buffer。

结论：最后那步 `AX_SYS_MemFree` 是**多余且错误**的——去 CMM 释放了一块归 IVPS pool 管、应用从未 `MemAlloc` 过的内存。

## Phase 5 收敛 + 证据分级

- **根因（强证据，已闭环）**：客户多调用 `AX_SYS_MemFree`，释放了不属于自己的 CMM 内存。依据：客户自查 + `Block not found` 日志 + 代码配对违反 + **删除后挂测一周不复现**。
- **挂死机制（中等证据，推断）**：多余的 `MemFree` 在部分时序下命中"该 phyaddr 已被复用"，误释放了别人正在用/正被 DMA 访问的内存 → 踩内存 → CPU1 硬挂。逐拍时序未在日志中直接抓到（硬挂无 backtrace；今可先开 ramoops/pstore 热重启读 `/sys/fs/pstore` 抓崩溃栈，当年客户最初因此上 JTAG），主要靠"改后不复现"闭环。
- 语义边界：`Block not found` 那行本身对应"非法 free 失败"一支，不致命；致命的是"free 成功 → 地址复用 → 再 free 误伤"一支。两者要分开表述。

## 修复

删掉最后的 `AX_SYS_MemFree`；帧交给 `AX_IVPS_ReleaseChnFrame` 归还即可；需 CPU 读数据时保留 `Mmap/Munmap` 成对使用。预防见 `fix-and-prevention.md`。

## 一句话总结

> 帧属于 IVPS pool，应用只是借用，`ReleaseChnFrame` 已归还；`AX_SYS_MemFree` 只能释放自己 `AX_SYS_MemAlloc` 的内存。多这一步等于去 CMM 释放别人的内存，在部分时序下把 CPU1 打挂——删掉即可，前四步本身没问题。
