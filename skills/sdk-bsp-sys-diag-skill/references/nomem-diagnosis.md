# 内存不足 (NOMEM / NOBUF) 快速诊断与定界

本文档为 Axera SoC SDK/BSP 系统层（SYS/CMM/Pool）的内存不足故障判据与定界指南。
当多媒体业务（VIN/ISP/IVPS/VENC/VO）出现**起流失败、中途断流、无码流、帧率异常暴跌**，且怀疑与内存相关时使用。

核心目标：**5 分钟内通过日志与 proc 状态抓出铁证，定性为内存不足，指出是哪类内存/哪个分区/哪个模块不足，并输出标准答复建议。**

---

## 一、 四大内存故障模式与判定特征

### 模式 A：CMM 连续物理分区耗尽 (NOMEM)
- **触发机制**：系统预留的 CMM 物理分区（如 `VIN0`、`venc0`、`anonymous` 等）总容量配小，或未针对当前分辨率/工作模式预留足够内存，导致底层物理分配器直接拒绝。
- **标志性日志**：
  ```text
  [SYS][E] [CMM][Error]: CMM partition memory isn't enough.
  [CMM][Error]: Partition name 'VIN0', Total=0MB, Free=56KB, nBlock=11
  ax_block_alloc(isp_regio_pipe_0_dyn, 84480, ...) failed!
  [VIN0:isp_regio_pipe_0_dyn]: mem agent malloc failed, type[0] size[84480]
  ax_regio_pipe_cmm_dyn_init failed, retval=0xffffffff
  PIPE_WRAPPER[0][open] failed!
  ax_vin_pipe_api_impl.c: pipe[0] ax_hal_pipe_open failed!
  ```
- **典型错误码**：`0x80110180`（VIN Pipe 启动失败）、`0x80110118`（VIN NOMEM）。
- **判定要点**：
  1. 确认具体的 Partition 名称（如 `VIN0`）；
  2. 比对该分区的 `Free` 空间与本次申请的大小（如剩余 56KB < 申请 84480 字节）；
  3. **结论定性**：属于系统静态配置/CMM 分区划分不足，非代码悬垂或越界。

---

### 模式 B：底层连续物理内存 Pool 创建失败
- **触发机制**：硬件编解码器或多媒体驱动尝试建立驱动专用缓冲池（Mbuf / Buffer Pool），由于连续物理内存不足或碎片化严重导致创建失败。
- **标志性日志**：
  ```text
  (VedfwlCreatePool|213) create pool failed. PoolName:H26xChn0Cuinfo
  (H26xEncCalInitCuInfoMbufPool|4065) Create CuInfo Pool bufsize:230400 BufNum:3 fail.
  (H26xEncCalSetCuInfoParam|9371) InitCuInfoMbufPool fail.
  VeChn0 CMD_SET_CUINFO_OUT_PARAM 0x80070218.
  AX_VENC_EnableSvc fail with ret:0x80070218
  ```
- **典型错误码**：`0x80070218`（VENC NOMEM）。
- **判定要点**：
  1. 日志出现 `create pool failed` 或 `Creat user pool fail!`；
  2. 错误码尾缀为 `0x18`（即标准错误码 `AX_ERR_*_NOMEM`）；
  3. 确认是否开启了某些非必需的重量级附加特性（如 CuInfo 输出等过度内存开销），或切分辨率时内存未规划。

---

### 模式 C：视频公共缓冲池 (VB/Mempool) 耗尽或引用泄漏 (NOBUF)
- **触发机制**：物理内存池已成功建立，但运行过程中分发给各个功能模块的块（Block）未及时归还，导致池中可用块归零。常见于**模块去使能/切分辨率时的异步时序竞争导致未调用 decref**。
- **标志性 Proc 节点证据**（查看 `/proc/ax_proc/mempool`）：
  ```text
  PoolId  Partition  PhysAddr    MetaSize  BlkSize  BlkCnt  FreeCnt  MinFreeCnt
  0       anonymous  0x4390C000  4096      3833856  5       0        0
  
  Index  BlockId     VIN  IVPS  VO  VENC  USER  ReqSize
  0      0x5E000000  1    0     0   0     0     3576960
  1      0x5E000001  0    0     1   0     0     3576960
  2      0x5E000002  0    0     1   0     0     3833856
  3      0x5E000003  0    0     1   0     0     737280
  4      0x5E000004  0    0     1   0     0     3833856
  ```
- **判定要点**：
  1. **`FreeCnt = 0`**：池中没有可用空闲块；
  2. **引用计数锁定**：检查引用矩阵（`VIN / IVPS / VO / VENC / USER`），若某一列大部分为 `1` 且长期不释放（例如上表 `VO` 占了 4 个块），说明该模块在特定生命周期（如 disable）漏调了引用计数递减；
  3. **级联断流**：上游因为拿不到 Free Block 无法吐帧，下游显示或编码出现 `InFps = 0.0`。

---

### 模式 D：编码码流环形缓冲满 (BufFull / 0x80070221)
- **触发机制**：VENC 码流缓冲区（Stream Ring Buffer）配置过小，或应用层取流不及时，编码硬件无处写入导致强行丢帧或中止。
- **标志性日志**：
  ```text
  (h26x_enc_cal.c) Chn0:BufFull={Qp=40, bLowLatEn=1, Seq=7, ReSize=99712, BsSize=475401}
  (enc_core.c) ChnId:0, abort, bBuffFull:1
  (h26x_enc_cal.c) Chn0, Ret:0x80070221, seqNum=38
  (h26x_enc_cal.c) Chn0 wait triger. please do get and release. drop frame
  ```
- **典型错误码**：`0x80070221`（`AX_ERR_VENC_BUF_FULL`）。
- **判定要点**：确认不是内存泄漏，而是码流缓冲区尺寸不足以容纳瞬时大 I 帧或消费端处理不及时。

---

## 二、 快速排查步骤（3 步收敛）

```text
步骤 1: 扫描日志关键字
  grep -E "CMM partition memory isn't enough|create pool failed|0x80070218|0x80110180|0x80110118|BufFull"
  ├── 命中 "CMM partition memory isn't enough"  ──> 判定为 [模式 A: CMM 分区不足]
  ├── 命中 "create pool failed" / 0x80070218    ──> 判定为 [模式 B: Pool 创建失败]
  └── 命中 "BufFull" / 0x80070221               ──> 判定为 [模式 D: 码流缓冲满]

步骤 2: 若系统未死，检查 /proc/ax_proc/mempool
  ├── FreeCnt == 0 且某一模块引用全为 1          ──> 判定为 [模式 C: VB 块耗尽 / 模块泄漏]
  └── FreeCnt > 0 且引用正常跳变                ──> 排除 VB 耗尽，转向业务流排查

步骤 3: 提取证据，输出标准答复结论
```

---

## 三、 标准答复与初因输出模板（脱敏规范）

在确认属于内存不足后，可直接按以下规范模板输出结论：

```markdown
### 【SYS 模块初因分析结论】

本故障确认由 **内存不足 (NOMEM / NOBUF)** 引起，具体定界如下：

1. **故障模式与定界**：
   - [ ] **CMM 分区不足**：`<分区名>` 分区总容量 `<Total>`，剩余 `<Free>`，本次申请 `<申请大小>` 失败。
   - [ ] **底层 Pool 内存不足**：Pool `<Pool名>` 申请单块大小 `<BlkSize>`、数量 `<BufNum>` 失败，返回错误码 `0x80070218`。
   - [ ] **VB 缓冲池耗尽 / 模块泄漏**：Pool `<PoolId>` 空闲块 `FreeCnt=0`，引用计数矩阵显示 `<模块名>` 长期持有未释放。
   - [ ] **码流环形缓冲满**：VENC 通道 `<Chn>` 发生 `BufFull`，错误码 `0x80070221`。

2. **关键日志证据**：
   ```text
   <粘贴 2~4 行最核心的报错日志，如 CMM partition memory isn't enough 或 create pool failed>
   ```

3. **处置与转派建议**：
   - 若属 CMM 分区不足：转派给系统应用/配置维护人员，调整分区脚本适当调大该分区容量，或在低内存配置下优化 buffer 深度。
   - 若属模块引用未释放：转派给对应业务模块（如 VO/VENC）排查切分辨率/去使能生命周期中的 decref 配对逻辑。
```
