# 修复与预防

## 一、直接修复（针对"取帧后又 MemFree"这类）

原则：**删掉那次多余/错误的释放**，让每对配对各归其位。以常见的多调 `MemFree` 序列为例：

```c
// ❌ 错误：最后多了一步 MemFree，释放了不属于自己的 IVPS 帧内存
AX_IVPS_GetChnFrame(grp, chn, &frame, ms);
void *vir = AX_SYS_Mmap(frame.u64PhyAddr[0], size);   // 需 CPU 访问时才映射
... 读/处理 ...
AX_SYS_Munmap(vir, size);
AX_IVPS_ReleaseChnFrame(grp, chn, &frame);
AX_SYS_MemFree(frame.u64PhyAddr[0], vir);              // ← 删掉这一行

// ✅ 正确：帧只归还给 IVPS；Mmap/Munmap 成对；不碰 MemFree
AX_IVPS_GetChnFrame(grp, chn, &frame, ms);
void *vir = AX_SYS_Mmap(frame.u64PhyAddr[0], size);    // 只转给硬件模块时可省略整段 Mmap/Munmap
... 读/处理 ...
AX_SYS_Munmap(vir, size);
AX_IVPS_ReleaseChnFrame(grp, chn, &frame);
```

要点：
- `AX_SYS_Mmap/Munmap` 是否需要，取决于**是否要 CPU 直接访问帧数据**（软件算法/叠加/dump 才需要；只转 VENC 等硬件模块可不映射）。
- `AX_SYS_Mmap` 返回的是临时映射地址，`Munmap` 后即失效，**绝不能**拿去 `MemFree`。
- 只有自己 `AX_SYS_MemAlloc` 出来的内存才 `AX_SYS_MemFree`。

## 二、预防规范（推给客户/团队，杜绝复发）

1. **token 规范化**：`AX_SYS_MemAlloc(..., "模块名")` 一律传有辨识度的 token（如 `qsvideo`/`venc_in`），出事时 `cat /proc/ax_proc/mem_cmm_info` 一眼看出 owner，反查 phyaddr 事半功倍。
2. **释放即清零**：`MemFree`/`Release` 成功后立刻把本地句柄清掉，避免 stale 值被二次释放：
   ```c
   if (phyaddr) { AX_SYS_MemFree(phyaddr, vir); phyaddr = 0; vir = NULL; }
   ```
3. **封装配对**：把 `Get → (Mmap → 用 → Munmap) → Release` 封成一个函数（或 C++ RAII / `goto err` 单出口），杜绝上层随手补一句 `MemFree`。
4. **Code review 硬规则**：见到 `Get*Frame` / `GetStream` / `GetBlock` 之后出现 `AX_SYS_MemFree`，直接打回。
5. **异常路径也要配对**：错误分支里别漏 `Release`/`Munmap`，也别重复 `Free`——用单出口清理最稳。

## 三、接口层根治方向（给 SDK/BSP 团队的建议）

`AX_SYS_MemFree(phyaddr, virAddr)` 只认地址值，天然挡不住 ABA（见 `cmm-ownership-rules.md` 第四节）。若要从接口层面防 stale free：
- **不可复用的 allocation handle**：`MemAlloc` 返回 `handle=index+generation`，`MemFree(handle)`；释放后 generation 递增，旧 handle 因 generation 不匹配而被拒。
- **owner / refcnt 校验**：block 记录 owner/allocation-id，释放时校验调用者身份，而非仅校验地址。
- **所有权明确**：`Get*` 只给"引用"，`Release*` 归还引用；除非 API 明确把 CMM block 所有权转移给调用者，否则调用者不得 `MemFree`。

> 注意：仅加锁只能解决并发时序，解决不了"旧调用者保存地址很久后再 free"的所有权问题——根治仍需 handle/generation/owner。
