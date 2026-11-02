# CMM 所有权：三对配对铁律与常见错法（Phase 4）

判断一次释放对不对，本质是问：**这块内存/这帧是谁申请的、归谁管、该由谁释放。** 跨所有权释放和重复释放，是本类挂死的根源。

## 一、三对配对铁律

每个"获取"接口都有唯一正确的"释放"接口，**绝不能交叉**：

| 获取 | 释放 | 归属体系 | 说明 |
|---|---|---|---|
| `AX_SYS_MemAlloc` / `MemAllocCached` | `AX_SYS_MemFree` | **CMM 直接分配** | 只有你自己 `MemAlloc` 出来的 CMM block，才由你自己 `MemFree` |
| `AX_SYS_Mmap` / `MmapCache` | `AX_SYS_Munmap` | **仅虚拟映射** | 只建立/解除用户态映射，**不涉及内存所有权**，绝不产生/消费内存 |
| `AX_IVPS_GetChnFrame` / `AX_VENC_GetStream` / `AX_VDEC_GetChnFrame` / `AX_POOL_GetBlock` … | 对应的 `AX_IVPS_ReleaseChnFrame` / `ReleaseStream` / `ReleaseChnFrame` / `AX_POOL_ReleaseBlock` | **模块 / pool 借用** | 借来的帧/块只能**归还**，归还即释放，绝不能再 `MemFree` |

在 AX615 SDK 源码里可自行印证（路径/行号以实际版本为准）：
- `AX_SYS_MemAlloc → ioctl_mem_cmm_alloc`、`AX_SYS_MemFree → ioctl_mem_cmm_free`（`msp/component/sys/ax_sys_api.c`）——都走 **CMM**。
- `AX_SYS_Mmap → ioctl_mem_cmm_mmap_std`、`AX_SYS_Munmap → ioctl_mem_cmm_munmap_v2`——**只映射**。
- `AX_IVPS_GetChnFrame → ivps_osal_frame_get`，返回的帧带 `u32BlkId`；`AX_IVPS_ReleaseChnFrame → ivps_osal_frame_release` 按 `u32BlkId` 归还（`msp/component/ivps/main/ax_ivps_adv_api.c`）——走 **IVPS pool**。
- pool 侧是 `ioctl_pool_getblock / releaseblock / increase_refcnt / decrease_refcnt`。

## 二、怎么判断一个 `Get*` 该用哪种释放

顺着实现看它落到哪套体系即可：
- 返回结构里带 `u32BlkId[]`、实现走 `*_frame_get` / `pool_getblock` → 属于 **pool/模块**，只能 `Release*` 归还，**不能 `MemFree`**。
- 实现走 `ioctl_mem_cmm_alloc` → 才是**你自己的 CMM**，用 `MemFree` 释放。
- 只是 `Mmap` 拿到的虚拟地址 → 用 `Munmap`，**它从不需要也不能 `MemFree`**。

一句话：**没亲手 `MemAlloc` 过的东西，就不要 `MemFree` 它。**

## 三、常见错法清单（逐条核对用户代码）

1. **取帧后又 MemFree**（最典型，标杆案例即此）：`GetChnFrame → (Mmap → 用 → Munmap) → ReleaseChnFrame → MemFree`。最后这步是错的——帧归 IVPS pool，`ReleaseChnFrame` 已完整归还，`MemFree` 会去 CMM 释放一块不归你管的内存。
2. **对 Mmap 地址 MemFree**：把 `AX_SYS_Mmap` 返回的临时虚拟地址（或帧里的 `u64VirAddr`）当作可释放内存传给 `MemFree`。
3. **同一 buffer 释放两次**：正常分支和异常分支各释放一次；或封装函数内外各释放一次。
4. **A 取 B 放，所有权不清**：一个模块/线程获取，另一个释放，退出时序一乱就重复或提前释放。
5. **释放后继续使用/再次释放**：`MemFree`/`Release` 后没把本地 `phyaddr/virAddr/handle` 清零，stale 值被后续代码再次释放。

## 四、为什么"同时传 phyaddr 和 virAddr"也挡不住（ABA）

`AX_SYS_MemFree(phyaddr, virAddr)` 只拿到两个**地址值**，不是不可复用的分配实例身份。时序：

```
A: MemAlloc → 得到 P/V
A: MemFree(P,V) → 成功，P 归还 CMM
X: 别处 MemAlloc → 恰好又拿到 P/V（地址被复用）
A: 旧代码再 MemFree(P,V) → P/V 仍"有效"，于是误释放了 X 的内存
```

即使映射关系也被复用，`phyaddr` 和 `virAddr` 两个值可以完全相同，内核无法区分"旧的 stale 参数"和"新的有效参数"。这是典型 **ABA 问题**——所以根治要靠**调用方摆正所有权**，接口层面则需 allocation handle / generation / owner 校验（见 `fix-and-prevention.md`）。
