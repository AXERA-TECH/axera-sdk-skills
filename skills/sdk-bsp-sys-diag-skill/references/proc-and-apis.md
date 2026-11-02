# 把 phyaddr 反查到 owner：proc 节点与用户态 API（Phase 3）

拿到 Phase 2 的 `phyaddr`（或 `BlockId`）后，这一步确定**这块内存到底是谁的**。owner 对不上释放者，就是跨所有权释放的铁证。

## 一、CMM proc 节点（最直接）

CMM 驱动（`kernel/osdrv/private_drv/sys/cmm/src/ax_cmm_proc_show.c`）会把每个分区、每个 block 打印出来。**每个 block 都带起止物理地址、大小和 `name`（即 `MemAlloc` 时传的 token = owner）。**

打印格式（见 `kernel/osdrv/private_drv/sys/cmm/include/osal_mmz.h`，字段以实际版本为准）：
```
+---PARTITION: Phys(0x43200000, 0x47E00000), Size=78MB, NAME="anonymous" ...
   |-Block:  phys(0x46208200, 0x46308200), cache=..., length=1024KB,  name="qsvideo"
                    ▲起址              ▲止址                              ▲owner token
```

用法（**节点名以实际为准**，不同版本可能是 `mem_cmm_info` / `ax_mem_info` / `cmm` 等，先 `ls` 找）：
```bash
ls /proc/ax_proc/                       # 找到 CMM 信息节点
cat /proc/ax_proc/mem_cmm_info          # 列出所有 partition/block: phyaddr/size/token
echo 'mem_cmm_info 1' > /proc/ax_proc/mem_cmm_info   # (可选) 开启用量调试:扫描 unused marker、使用率
```

**判读**：把 Phase 2 记下的 `phyaddr` 落进某个 block 的 `[起址, 止址]` 区间，看它的 `name=`：
- owner 是 **IVPS / pool / 某底层模块**，而**释放它的是应用线程** → 跨所有权释放，指向应用错误 `MemFree`（标杆案例即此）。
- 建议**复现前先 dump 一份**（挂死后往往取不到），作为对照基线。

> 前提：`MemAlloc` 时 token 要有辨识度（模块名），否则 proc 里全是 `null`/`anonymous`，反查会很吃力。见 `fix-and-prevention.md` 的 token 规范。

## 二、用户态查询 API（在代码里现场反查）

来自 `header/external/ax_sys_api.h`（签名以实际版本为准）：

| API | 作用 | 诊断用途 |
|---|---|---|
| `AX_SYS_MemGetBlockInfoByPhy(phyaddr, &memType, &virAddr, &blockSize)` | 按**物理地址**查内存类型/虚拟地址/块大小 | **释放前确认**"这块到底是不是有效 CMM block、多大、什么类型"，不确定就别 `MemFree` |
| `AX_SYS_MemGetBlockInfoByVirt(virAddr, &phyaddr, &memType)` | 按**虚拟地址**反查物理地址/类型 | 手里只有 virAddr 时定位 |
| `AX_SYS_MemGetPartitionInfo(&partInfo)` | 查 CMM 分区布局 | 判断某地址落在哪个分区 |
| `AX_SYS_MemQueryStatus(&cmmStatus)` | 查 CMM 总量/已用/剩余 | 辅助判断是否泄漏 |
| `AX_SYS_MemGetMaxFreeRegionInfo(&phyaddr, &size)` | 查最大连续空闲区 | 判断碎片/耗尽 |

## 三、VB / Mempool 节点状态判读（诊断 NOBUF / 块泄漏）

针对运行中无码流、断流、起流失败但不是物理内存不足的场景，排查 `/proc/ax_proc/mempool`：

```bash
cat /proc/ax_proc/mempool
```

打印格式示例：
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

**判读规则**：
1. **看 `FreeCnt`**：为 0 且 `MinFreeCnt=0` 表示池中可用 Buffer 已耗尽。
2. **看引用计数矩阵（Ref Matrix）**：
   - 正常流转时各列应该在 0 和 1 间跳变；
   - 若发现大部分块卡在某单列（如上例 `VO: 1` 占了 4 个块），说明该模块在特定路径（如切分辨率/去使能）存在引用计数泄漏（未执行 `decref`）。

## 四、把结论接到 Phase 4 或内存定界结论

- owner 明确不是释放方 → 直接进 Phase 4 审调用配对，基本可判"错误释放"。
- owner 就是释放方本人 → 说明不是跨所有权释放，转向"重复释放/释放后使用"或其它诊断路径。
- 若 `FreeCnt=0` 且有引用积压 → 转 `references/nomem-diagnosis.md` 判定为 VB 耗尽/泄漏。
