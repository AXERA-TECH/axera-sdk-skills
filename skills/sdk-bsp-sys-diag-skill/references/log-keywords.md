# 日志关键字判读（Phase 2）

拿到日志后，先跑 `scripts/scan_cmm_log.sh <logfile>` 做一次全量扫描，再对照下表逐条理解。**核心动作：记下报错里的 `phyaddr=0x...`，它是 Phase 3 反查 owner 的锚点。**

## 关键字对照表

| 日志关键字（grep 用） | 出处 / 含义 | 下一步动作 |
|---|---|---|
| `ax_cmm_free failed! Block not found,phyaddr=0x...` | CMM 驱动（`kernel/osdrv/private_drv/sys/cmm/src/ax_cmm_ext.c`）里 `ax_cmm_free` 按物理地址在 CMM block 表中**查不到**该 block。说明发生过**非法/重复/跨所有权的释放**（对不属于自己、或已释放的地址调 `MemFree`）。 | 抽出 `phyaddr`，进 Phase 3 反查 owner；进 Phase 4 审调用配对 |
| `[Pool][Func]:ioctl_pool_handle2poolid ... BlockId :0x.. invalid!`、`handle2physaddr fail`、`getblockviraddr failed` | pool 侧用一个**已失效的 BlockId**去换 poolid/物理地址/虚拟地址。常见于对象已被释放/归还后仍被使用。 | 记下 BlockId；结合上下文看是哪个模块在用失效句柄 |
| `giveback_to_pool ... frame node virt get fail u32BlkId 0x...` | 归还帧到 pool 时，该 block 的虚拟地址已取不到（block 已无效）。指向**生命周期/释放顺序**问题。 | 关联该 BlkId 与取帧/放帧序列 |
| `X blocks are not free, CMM<..> should not be unregistered!`（后面通常跟 `|-Block: ...` 明细） | 退出反注册 CMM 分区时，仍有 block 未释放（**泄漏或被错误持有**）。 | 看未释放 block 的 name(token)，定位漏放的模块 |
| `CMM partition memory isn't enough.` / `mem agent malloc failed` / `ax_block_alloc... failed` | CMM 物理分区剩余容量不足（**NOMEM**），通常紧跟打印对应 Partition 的 Total、Free 与申请失败的 size。 | 详见 `references/nomem-diagnosis.md`；记录分区名与差值 |
| `create pool failed` / `Creat user pool fail!` / `Init...MbufPool fail` | 底层连续物理内存不足，无法创建指定规格的驱动 Mbuf/Buffer Pool（**NOMEM**）。 | 详见 `references/nomem-diagnosis.md`；核查 PoolName 与 bufsize |
| 错误码 `0x80070218` / `0x80110118` / `0x80110180` | 分别对应 VENC NOMEM、VIN NOMEM、VIN Pipe 启动失败。标准内存不足返回码。 | 确认调用接口，转 `references/nomem-diagnosis.md` |
| `BufFull` / `bBuffFull` / 错误码 `0x80070221` | VENC 码流环形缓冲满（`AX_ERR_VENC_BUF_FULL`），硬件无处写入导致丢帧。 | 确认 Stream Ring Buffer 大小及取流时效 |
| `ivps_sched_chn_disable` / `ax_base_sync_agent_session_deinit` / `VENC_CAL_StopRecvPic` / `AX_..._Deinit` 附近 | 这些是**退出/销毁流程**的标志。若 CMM/pool 报错夹在其间，说明问题发生在退出路径。 | 用它定位出问题的模块与时序 |

## 如何抽取 phyaddr

```bash
grep -oE 'phyaddr=0x[0-9a-fA-F]+' <logfile> | sort -u
grep -oE 'BlockId :0x[0-9a-fA-F]+' <logfile> | sort -u
```

把这些地址/ID 交给 Phase 3 去反查 owner。

## 语义边界（做证据分级时很重要）

- `ax_cmm_free ... Block not found` 这行**只证明"发生过一次非法 free"**（对应"第二次 free 失败"那一支），它本身**不直接等于挂死**。
- 真正打成挂死的，通常是另一支：**free 成功 → 该物理地址被重新分配给别人 → 旧调用者又拿旧地址 free → 误释放了别人正在用的内存 → 踩内存 → 硬挂**。这一支的**逐拍时序在普通日志里往往抓不到**（硬挂时连 backtrace 都出不来）。
- 因此：看到 `Block not found` 可以下"确实存在非法/重复释放"（强证据）；但"它就是通过误释放他人内存这条路径挂的"要标为**推断（中等证据）**，靠"改掉多余释放后不复现"来闭环。详见 `root-cause-decision-tree.md`。
