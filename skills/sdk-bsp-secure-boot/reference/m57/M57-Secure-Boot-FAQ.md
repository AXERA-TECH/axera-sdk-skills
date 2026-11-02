# M57 Secure Boot FAQ

## 快速检查清单

首次启用时，建议按以下顺序执行：

1. 明确目标平台、启动介质、是否启用 A/B、RSA-2048 或 RSA-3072、是否加密固件、是否保护 rootfs。
2. 离线生成并妥善保管 RSA 私钥；需要固件加密时再准备 256-bit AES Key。
3. 替换 SDK 签名密钥，并同步更新 U-Boot DTS 中对应的 RSA 公钥参数。
4. 修改目标平台的 `build/platforms/<vendor>/<platform>/config.mk`。
5. 保持 eFuse Secure Boot/加密开关未使能，先编译、烧写并跑通完整签名链。
6. 检查各阶段串口日志、最终打包使用的镜像名和 A/B slot，完成篡改镜像负向测试。
7. 通过量产评审后，再按《AX EFUSE 使用说明》烧写并复核 PKH；需要密文启动时，按规定顺序准备 Root Key 和 FEK。

---

## 基本概念

### Q1：M57 Secure Boot 保护哪些启动阶段？

完整信任链如下：

| 当前阶段 | 校验的下一级对象 | 主要机制 |
|---|---|---|
| BootROM | SBL | SBL 固定 header、SHA-256、RSA 签名；eFuse Secure Boot 使能后还校验 header 中公钥的 PKH |
| SBL | SPL、AutoSAR/RTOS | 镜像 header、SHA-256、RSA 签名 |
| SPL | ATF、OP-TEE、U-Boot | U-Boot FIT 签名校验 |
| U-Boot | Kernel、rootfs root hash | Kernel FIT 签名；rootfs root hash RSA 签名 |
| Linux | rootfs 数据块 | dm-verity hash tree 按需校验 |

任一阶段校验失败，后续阶段都不应继续执行。HSM 为镜像验签和解密提供硬件加速。

### Q2：签名、加密和 dm-verity 有什么区别？

- **签名**解决真实性和完整性问题：设备确认镜像来自受信密钥且未被修改。
- **加密**解决固件机密性问题：`ENABLE_CIPHER=TRUE` 时，启动阶段通过 eFuse 中受保护的密钥材料解密固件。
- **dm-verity** 解决只读 rootfs 的运行期按块完整性问题：U-Boot 只验证 root hash 的签名，Linux 在读取文件系统块时沿 hash tree 校验数据。

三者不能互相替代。rootfs 当前不做固件加密；需要保护 rootfs 时使用 `ROOTFS_DMVERITY`。

### Q3：软件配置和 eFuse Secure Boot 有什么关系？

SBL header 的 `security_attr` 和 eFuse Bond Option 共同决定 BootROM 行为：

- **eFuse Secure Boot 已使能**：一定进入安全启动，并校验 SBL header 中公钥对应的 eFuse PKH。
- **eFuse Secure Boot 未使能、SBL header 标记 Secure Boot**：仍会进行镜像签名校验，但 BootROM 不以 eFuse PKH 约束该公钥。
- **两者均未使能**：不会形成强制的硬件信任根。

因此可以先在未烧写 eFuse 的开发板上验证签名链。这是烧写不可逆配置前必须完成的阶段，不代表量产安全状态已经建立。

### Q4：为什么开启 eFuse 后不能再启动普通镜像？

eFuse Secure Boot 使能后，BootROM 会强制执行安全启动并校验 PKH。没有正确 header、签名、公钥或 PKH 不匹配的 SBL 都会被拒绝。开启固件加密 Bond Option 后，只能启动与设备 Root Key/FEK 匹配的密文 SBL。

> **警告：** 在签名镜像、PKH 和恢复路径尚未验证前，不要使能 eFuse Secure Boot；在 Root Key、FEK 与 AES Key 的对应关系尚未验证前，不要使能固件加密。

---

## 配置与编译

### Q5：Secure Boot 在哪里配置？

修改目标平台文件：

```
build/platforms/<vendor>/<platform>/config.mk
```

例如 AX637 eMMC 平台使用：

```
build/platforms/axera/ax637_demo_only_emmc/config.mk
```

关键配置如下：

```makefile
SECURE_BOOT     := TRUE
ENABLE_CIPHER   := FALSE
SIGN_USE_RSA3072 := FALSE
ROOTFS_DMVERITY := FALSE
ROOTFS_FS_TYPE  := EXT4
```

使用 `make -C build PLAT=<platform>` 进入现有顶层构建流程；具体全量、组件或打包目标沿用项目已有构建说明。产物位于：

```
build/out/<platform>/images/
```

### Q6：四个关键配置项分别控制什么？

| 配置 | 作用 | 约束 |
|---|---|---|
| `SECURE_BOOT` | 编译安全启动代码并生成/打包签名镜像 | 加密和 dm-verity 的前提 |
| `ENABLE_CIPHER` | 生成并选用密文签名启动镜像 | 必须先启用 `SECURE_BOOT`，设备需正确配置 Root Key/FEK |
| `SIGN_USE_RSA3072` | `TRUE` 使用 RSA-3072，否则使用 RSA-2048 | 密钥文件、DTS 公钥节点、镜像算法必须一致 |
| `SIGN_USE_RSA_PSS` | `TRUE` 使用 RSA-PSS 填充，`FALSE` 使用 RSA-PKCS#1-v1.5 | 只影响 SBL 之后的 SPL/ATF/OP-TEE/U-Boot/Kernel FIT 签名；SBL 恒用 PKCS#1-v1.5 |
| `ROOTFS_DMVERITY` | 生成并选用 `rootfs_signed.img` | 必须先启用 `SECURE_BOOT`；不支持 UBI |

平台 `config.mk` 已包含组合检查：`SECURE_BOOT=FALSE` 时不允许开启 `ENABLE_CIPHER` 或 `ROOTFS_DMVERITY`，`ROOTFS_FS_TYPE=UBI` 时不允许开启 dm-verity。

### Q7：dm-verity 支持哪些 rootfs 类型？

支持只读 EXT4 或 SQUASH，不支持 UBI。源码构建流程使用 `veritysetup format` 生成 hash tree/root hash，再由 `rootfs_sign.py` 对 root hash 签名并输出 `rootfs_signed.img`。

启用后还要确认：

- rootfs 分区留出了 verity header、hash tree 和签名空间；当前 `rootfs/Makefile` 会根据分区大小预留空间。
- Kernel 配置包含 `CONFIG_BLK_DEV_DM=y`、`CONFIG_DM_INIT=y` 和 `CONFIG_DM_VERITY=y`。
- 实际烧写和打包选择的是 `rootfs_signed.img`，而不是 `rootfs.img`。

### Q8：不同配置会生成并打包哪些镜像？

| 组件 | 非 Secure Boot | 签名 | 加密并签名 |
|---|---|---|---|
| SBL | `sbl_signed.img`¹ | `sbl_signed.img` | `sbl_enc_signed.img` |
| AutoSAR/RTOS | `Mcal_Demo_signed.img`¹ | `Mcal_Demo_signed.img` | `Mcal_Demo_enc_signed.img` |
| SPL | `u-boot-spl_signed.img`¹ | `u-boot-spl_signed.img` | `u-boot-spl_enc_signed.img` |
| U-Boot | `u-boot.img` | `u-boot_signed.img` | `u-boot_enc_signed.img` |
| ATF | `bl31.img` | `bl31_signed.img` | `bl31_enc_signed.img` |
| OP-TEE | `optee.img` | `optee_signed.img` | `optee_enc_signed.img` |
| Kernel | `kernel.img` | `kernel_signed.img` | `kernel_enc_signed.img` |
| rootfs | `rootfs.img` | `rootfs.img` 或启用 dm-verity 后的 `rootfs_signed.img` | 不支持加密；dm-verity 仍使用 `rootfs_signed.img` |

¹ SBL、RTOS 和 SPL 的基础产物名称带 `_signed`，但只有 header/编译配置标记 Secure Boot 时才构成启用的签名校验链，不能仅凭文件名判断安全状态。

最终 AXP/SWU 选图由顶层配置驱动。排查时不能只确认某个文件"已经生成"，还要确认打包脚本实际选择的文件名、分区和 slot。

### Q9：为什么编译成功，但打包后设备仍加载了非安全镜像？

常见原因是只生成了安全镜像，没有让打包配置选中它。检查：

1. 目标平台 `config.mk` 中的配置，而不是其他平台的同名文件。
2. `build/out/<platform>/images/` 中目标文件是否存在且时间戳正确。
3. AXP/SWU 构建是否收到 `SECURE_BOOT`、`ENABLE_CIPHER`、`ROOTFS_DMVERITY` 标志。
4. 包内 U-Boot、Kernel、rootfs 及 A/B 两个 slot 是否都选择了同一套安全产物。
5. ATF/OP-TEE 仅在对应 `SUPPORT_ATF`/`SUPPORT_OPTEE` 开启时参与打包。

源码 `build/scripts/axp_make.sh` 在 `SECURE_BOOT=TRUE` 时选择 `u-boot_signed.img` 和 `kernel_signed.img`；再根据 `ENABLE_CIPHER` 切换到 `*_enc_signed.img`，根据 `ROOTFS_DMVERITY` 切换到 `rootfs_signed.img`。

---

## 密钥与公钥

### Q10：RSA-2048 和 RSA-3072 如何选择？

`SIGN_USE_RSA3072=FALSE` 使用 RSA-2048，`TRUE` 使用 RSA-3072。当前源码对应路径为：

| 算法 | 私钥 | 公钥 | U-Boot DTS 节点 |
|---|---|---|---|
| RSA-2048 | `tools/imgsign/private.pem` | `tools/imgsign/public.pem` | `key-akcipher2048` |
| RSA-3072 | `tools/imgsign/key_3072/private.pem` | `tools/imgsign/key_3072/pubkey.pem` | `key-akcipher3072` |

算法切换不是只改一个开关：签名文件、U-Boot DTS 公钥、eFuse PKH 和待启动镜像必须属于同一套密钥。

### Q11：如何替换自己的 RSA 密钥？

在受控的 Linux 服务器离线环境生成传统 PEM 格式 RSA 私钥及对应公钥，将构建所用文件替换为 Q10 所列路径。不要把生产私钥提交到源码仓库、构建日志、工单或支持附件。

```bash
# 生成私钥（2048；3072 改位数）
openssl genrsa -out private.pem 2048
# 导出公钥 —— 必须加 -RSAPublicKey_out，得到 PKCS#1（"BEGIN RSA PUBLIC KEY"）格式
openssl rsa -in private.pem -pubout -RSAPublicKey_out -out public.pem
```

> 注意：不能用默认的 `openssl rsa -pubout`（生成 SPKI `BEGIN PUBLIC KEY` 格式）；SDK 签名工具与
> `sample_efuse_key` 均按 PKCS#1 格式解析。

替换后执行：

```bash
python3 build/scripts/extract_pkey_param.py -k tools/imgsign/public.pem
```

RSA-3072 时将输入路径改为 `tools/imgsign/key_3072/pubkey.pem`。把输出参数写入：

```
boot/uboot/u-boot-2022.10/arch/arm/dts/m57-keys.dtsi
```

RSA-2048 更新 `key-akcipher2048`，RSA-3072 更新 `key-akcipher3072`。指南中出现的 `m57h-keys.dtsi` 与当前源码不一致，当前仓库应以 `m57-keys.dtsi` 为准。

### Q12：为什么替换签名 PEM 后还要修改 m57-keys.dtsi？

SPL 和 U-Boot 校验 FIT 镜像时，从自身 DTB 的 `signature` 节点取得公钥参数，不会在每次 FIT 校验时直接读取 eFuse PKH。若 PEM 已替换而 DTS 仍是旧公钥，则 ATF、OP-TEE、U-Boot、Kernel 或 rootfs root hash 会验签失败。

关系理解：

- **BootROM/SBL 前段**：镜像 header 携带公钥；eFuse Secure Boot 使能后，PKH 约束该公钥是否合法。
- **SPL/U-Boot 后段**：运行镜像的 DTB 内嵌公钥，用它验证下一级 FIT/root hash。

因此，签名私钥、对应公钥、DTB 公钥参数、PKH 和镜像必须作为一个版本化集合管理。

### Q13：AES Key、Root Key 和 FEK 是同一个东西吗？

不是。

- **`tools/imgsign/aes-256.key`**：构建侧用于加密启动镜像的 32-byte AES Key 表示。
- **Root Key（RTK）**：设备 eFuse 中的根密钥材料，应先于依赖项配置，写入后 CPU 不可直接读出。
- **FEK**：与固件 AES Key 对应、经 Root Key 保护后的设备侧材料；Root Key 不同，FEK 结果也不同。

不需要密文启动时，不需要启用 `ENABLE_CIPHER`，也不需要为 Secure Boot 单独烧写 FEK。rootfs 本身不使用该固件加密路径。

`aes-256.key` 是文本格式的 64 个 hex 字符，生成命令：

```bash
openssl rand -hex 32 > tools/imgsign/aes-256.key
```

SDK 自带的 `aes-256.key` 为全 0 占位值，不可用于量产。烧写 FEK 与密钥材料见 Q13b。

### Q13b：如何烧写 Root Key / PKH / FEK，以及 bondoption？

密钥材料用 `sample_efuse_key`（`msp/sample/efuse_key/`），bondoption 用 `sample_efuse`
（`msp/sample/efuse/`），两者不可混用：

| 工具 | 命令 | 用途 |
|---|---|---|
| `sample_efuse_key` | `rootkey random` | HSM 随机生成并烧写 256-bit Root Key（blk15–22），置 rootkey protect |
| `sample_efuse_key` | `pubkey <key_idx> <pubkey_pem>` | 烧写 RSA 公钥 SHA-256 到 PKH slot（0/1/2） |
| `sample_efuse_key` | `aeskey` | 用 Root Key 封装 AES Key 得 FEK 并烧写（blk65–74） |
| `sample_efuse` | `-w 64 0x1` / `-w 14 0x4000` 等 | 烧写 bondoption：blk64 bit0=secure boot、bit1=encrypt、bit2=pkh flag1；blk14 bit14=pkh flag0 |

关键限制：

- `sample_efuse_key` 源码 `EFUSE_WRITE_ENABLE` 默认 0，只打印不写入；真正烧写需改 1 重新编译（`hsmhuk` 不受此控制）。
- `sample_efuse_key aeskey` 写死 `aeskey_static_array` 固定测试值，不可量产；烧写自定义 AES Key 需改源码，
  或走 U-Boot `ax_efuse_key aeskey <addr>`（从内存地址读 32-byte 明文 AES Key）。
- `sample_efuse` 写 blk14/blk64 前会 `bondopt_check()` 预检：将使能 secure boot 而对应 PKH 未烧写、
  或使能 encrypt firmware 而 FEK 未烧写时取消写入，防止砖化。

烧写顺序：先 Root Key → 再 FEK（加密时）→ 烧 PKH → 最后使能 secure boot / encrypt 位。

### Q14：PKH 有什么作用？为什么建议规划三组？

PKH 是 RSA 公钥的 SHA-256 值。BootROM/SBL 在 eFuse Secure Boot 强制状态下，用选中的 PKH 区域判断镜像 header 中的公钥是否合法，然后才使用该公钥验签。

M57 预留多个 PKH 区域，并由 Bond Option 选择。生产阶段可规划三组不同 RSA 密钥以支持密钥轮换或产品策略切换；具体区域、选择位、写入和锁定步骤必须以《AX EFUSE 使用说明》和产品 eFuse 规划为准，不能根据 FAQ 猜测烧写。

---

## 验证与量产导入

### Q15：烧 eFuse 前应该怎样验证？

至少完成以下测试：

1. 保持 eFuse Secure Boot 未使能，使用 `SECURE_BOOT=TRUE` 的完整镜像启动。
2. 确认 SBL、SPL、可选 ATF/OP-TEE、U-Boot、Kernel、rootfs 均进入预期阶段。
3. 分别替换一个被篡改的 SBL/SPL/FIT/Kernel，确认在负责校验它的阶段停止启动。
4. 启用 dm-verity 时，先确认 U-Boot root hash 验签，再篡改 rootfs 数据块，确认 Linux 读取时报告校验失败。
5. A/B 产品分别验证 slot A 和 slot B，确认失败记录中的 slot 与实际一致。
6. 记录 RSA 算法、公钥指纹/PKH、构建版本、配置、包内镜像清单和串口日志，作为 eFuse 烧写评审输入。

如需密文启动，应先在专用测试芯片上验证 Root Key、FEK、AES Key 和密文镜像的一致性。任何一项不确定都不能进入不可逆烧写。

### Q16：怎样确认 dm-verity 真正在工作？

不能只看 U-Boot 的 root hash 验签成功。建议分三层确认：

1. **构建层**：存在 `rootfs_signed.img`，日志显示 `veritysetup format` 和 root hash 签名完成。
2. **启动层**：U-Boot 成功解析 verity header、验证 root hash 签名，并在 `bootargs` 中加入 `dm-mod.create=...`。
3. **运行层**：Linux 创建 dm-verity 映射并通过该设备挂载只读 rootfs；对底层数据块做受控篡改后，访问相应文件应产生 I/O/verity 校验错误。

U-Boot 不会为了验签而读完整个 rootfs。某个尚未访问的数据块被破坏，可能直到 Linux 读取该块时才暴露。

### Q17：能否在 Secure Boot 下继续更新镜像？

可以，但新镜像必须满足当前设备信任链：

- 使用设备接受的签名密钥和算法。
- 加密设备使用匹配的 AES Key/FEK 关系。
- dm-verity rootfs 必须重新生成 hash tree、root hash 和签名，不能只替换文件系统数据区。
- A/B 更新必须为目标 slot 写入完整且一致的组件集合。

Secure Boot 不等于防回滚。若产品要求禁止启动旧的合法签名版本，还需单独规划并验证 Anti-Rollback。

---

## Download 安全

### Q18：什么时候会校验 Download 使用的 FDL 签名？

**只有芯片 eFuse 已使能 Secure Boot 时，BootROM 才会在 Download 流程中强制校验 FDL 签名。** 使用 AXDL 时不需要再配置一个独立的"Download 验签"开关。

- **eFuse Secure Boot 未使能**：Download 流程不会因为平台 `config.mk` 中的 `SECURE_BOOT=TRUE` 而单独强制校验 FDL 签名。
- **eFuse Secure Boot 已使能**：只有公钥合法且 RSA 签名正确的 FDL 才能执行；BootROM 先校验 FDL1，FDL1 再校验 FDL2。任一级校验失败都会返回安全签名错误，不能执行对应 FDL。
- eFuse 中的 USB、SD、UART、CAN Download 禁用位与 FDL 验签是两类控制：前者决定接口能否使用，后者决定收到的 FDL 是否可信。

因此，量产烧写 eFuse Secure Boot 前，必须确认 AXDL 包中的 FDL 使用了与设备 PKH 对应的 RSA 密钥签名，否则设备可能进入 Download 接口后仍无法运行 FDL。

### Q19：Download 使用的 FDL 是否需要加密？

不需要。M57 SDK 的 Download FDL 只签名，不加密：

- FDL 使用 RSA-2048 或 RSA-3072 签名，算法选择应与设备接受的公钥和 PKH 一致。
- `ENABLE_CIPHER=TRUE` 控制 SBL、SPL、RTOS、ATF、OP-TEE、U-Boot 和 Kernel 等启动镜像的加密，不会把正常 SDK/AXDL 流程使用的 FDL 改成加密 FDL。
- 不要因为设备启用了固件加密，就寻找或制作 `fdl*_enc_*` 产物；应使用 SDK 打包的签名 FDL。

当前打包流程中的典型安全 FDL 文件名为 `fdl1_signed.img` 和 `fdl2_signed.img`。文件名带 `_signed` 表示包含签名信息；是否在 Download 时强制验签，仍取决于设备 eFuse Secure Boot 状态。eFuse Secure Boot 已使能时，AXDL 包中的 FDL1 和 FDL2 都必须使用匹配密钥签名，不能只替换其中一个。

---

## 故障定位

### Q20：安全启动失败时，第一时间收集什么？

不要先反复刷写。保留以下信息：

- 板型、芯片和启动介质，当前 slot 及 A/B 状态。
- 完整串口日志，从复位开始，不只截最后一行。
- SDK/提交版本及目标平台 `config.mk` 的四个关键配置。
- 实际烧写/包内镜像文件名及校验值。
- RSA-2048/3072 选择、公钥指纹或 PKH 标识；不要提供私钥、AES Key、Root Key 或 FEK 内容。
- eFuse Secure Boot、加密和 PKH 选择状态的获批只读结果。
- 失败发生在 BootROM、SBL、SPL、U-Boot 还是 Linux。

### Q21：BootROM 阶段出现 trace 时，如何判断是哪种 Secure Boot 异常？

先区分串口短码和 trace 位图。BootROM 失败时会输出 `BS 0x... BN` 形式的 trace 汇总；其中包含 `BOOT` 和 `SECURE` 两个安全启动相关字段。按当前 M57 BootROM trace 字段顺序，从 `BS` 后第一个 32-bit 数据开始计数：`BOOT` 是第 5 个，`SECURE` 是第 9 个；`BS` 前缀本身不计数。每个字段是按位或累积的标志，不是十进制错误码。

常见的 BootROM 安全启动标志如下，掩码用于对对应的 trace 数值做按位与判断：

| BOOT_DEBUG_FLAG 标志（掩码） | 串口短码 | 含义与优先检查项 |
|---|---|---|
| `BOOT_READ_CE_FW_FAIL (0x00000800)`、`BOOT_VERIFY_CE_FW_FAIL (0x00001000)` | RF、CF | HSM/CE 固件读取失败或可选 checksum 失败；先查存储读、header 的固件位置和镜像完整性 |
| `BOOT_SECURE_INIT_FAIL (0x00010000)` | SIF | HSM/CE 初始化或等待就绪失败；先查固件加载、HSM 状态，再看 SECURE 中的 `SEC_DBG_INIT_FAIL (0x1)` |
| `BOOT_AES_DECRYPTO_FAIL (0x00080000)` | DF | SBL 解密失败；核对密文 SBL、加密开关及设备 Root Key/FEK 与构建 AES Key 的关系 |
| `BOOT_READ_S_IMG_HEADER_FAIL (0x80000000)` | R2F | 签名所需的第二段 SBL header 读取失败；先查存储介质和镜像写入，不要误判为验签失败 |
| `BOOT_VERIFY_PUBKEY_FAIL (0x00020000)` | PKF | SBL header 公钥校验失败；结合下表区分 eFuse 读、hash 和 PKH 不匹配 |
| `BOOT_CIPHER_SHA_FAIL (0x00040000)` | SHF | SBL 镜像 SHA-256 计算失败；检查 HSM 状态及镜像读取路径 |
| `BOOT_VERIFY_RSA_FAIL (0x00100000)` | RSF | SBL RSA 签名验签失败；核对签名密钥、RSA 位数、镜像数据及签名 |

若 PKF 伴随 `BOOT_VERIFY_PUBKEY_FAIL`，继续查看同一条 trace 的 `SECURE` 值，并按 `SECURE_DEBUG_FLAG` 解释：

| SECURE_DEBUG_FLAG 标志（掩码） | 进一步定位 |
|---|---|
| `SEC_DBG_EFUSE_INIT_FAIL (0x2)` | eFuse 初始化失败 |
| `SEC_DBG_READ_KEY_HASH_FAIL (0x8)` | 选中的 eFuse PKH 读取失败 |
| `SEC_DBG_HASH_KEY_FAIL (0x10)` | 对 header 公钥计算 SHA-256 失败 |
| `SEC_DBG_KEY_VERIFY_FAIL (0x20)` | eFuse Secure Boot 已使能，header 公钥 hash 与选中 PKH 不匹配 |

`SEC_DBG_KEY_VERIFY_PASS (0x40)` 只表示本次公钥检查通过；如果设备 eFuse Secure Boot 未使能，PKH 可能不会参与强制比对，不能据此断定芯片已建立硬件信任根。`BOOT` 中的 `BOOT_FAIL (0x20000000)` 仅表示本次 flash 启动失败；RF/CF 还可能是普通 header/镜像读取或 checksum 失败，不一定是安全异常。

位图在一次 BootROM 启动中累积，且失败后可能切换 slot 或重试；应保留完整原始 `BS ... BN`、紧邻的短码和 slot，按当前版本标志定义逐位核对。串口无输出时还需检查 UART 是否被禁用，或波特率是否配置正确；重启后不要依赖上一次启动留下的 trace 值。

**示例**（header 公钥与 eFuse PKH 不匹配）：

```
: PKF
trace: BS 0x00000000 0x00000000 0x00000000 0x00000000 0x00020000 0x00000000 0x00000000 0x00000000 0x00000020 ... BN
```

解码：
1. `PKF` 是串口短码，表示公钥校验失败。
2. `BOOT` 字段为 `0x00020000`，置位 `BOOT_VERIFY_PUBKEY_FAIL`，表示 SBL header 的公钥校验未通过。
3. `SECURE` 字段为 `0x00000020`，置位 `SEC_DBG_KEY_VERIFY_FAIL`，表示 eFuse Secure Boot 强制状态下，header 公钥 hash 与选中的 PKH 不匹配。
4. 该示例应优先检查 RSA 公钥、PKH 选择、签名镜像和目标 slot 是否属于同一套密钥配置。

### Q22：BootROM Download 失败时，如何通过 DOWNLOAD_DEBUG_FLAG 定位 Download 验签失败？

BootROM 校验 FDL1 时产生的 Download trace 通常以 `DS 0x... DN` 输出。从 `DS` 后第一个 32-bit 数据开始计数，第 5 个 32-bit 数据是 `DOWNLOAD_DEBUG_FLAG`，`DS` 前缀本身不计数。如果日志输出的是完整 `BS 0x... BN` trace，则 `DOWNLOAD_DEBUG_FLAG` 是第 12 个 32-bit 数据。FDL2 由 FDL1 校验，失败时还应结合 AXDL 返回的安全签名错误和 FDL1 串口日志定位。

| DOWNLOAD_DEBUG_FLAG 标志 | 掩码 | 含义 |
|---|---|---|
| `DL_HANDSHAKE_OK` | `0x00000001` | Download 握手成功 |
| `DL_SEND_VER` | `0x00000002` | 已发送版本信息 |
| `DL_CE_INIT_FAIL` | `0x00000004` | HSM/CE 初始化失败 |
| `DL_CE_WAIT_INIT_FAIL` | `0x00000008` | 等待 HSM/CE 就绪超时或失败 |
| `DL_VERI_HEAD_FAIL` | `0x00000010` | FDL image header 校验失败 |
| `DL_PUB_KEY_VERI_FAIL` | `0x00000020` | FDL 公钥合法性校验失败，优先核对设备 PKH 与 FDL 公钥 |
| `DL_SHA_FAIL` | `0x00000040` | FDL 镜像 SHA-256 计算失败 |
| `DL_RSA_FAIL` | `0x00000080` | FDL RSA 签名验签失败 |
| `DL_SECURE_SUCC` | `0x00000100` | FDL 安全校验成功 |
| `DL_OK` | `0x00000200` | 当前 Download 传输阶段成功完成 |
| `DL_EIP_READ_END` | `0x00000400` | HSM/CE 固件接收完成 |
| `DL_WAIT_CE_INIT` | `0x00000800` | 已进入等待 HSM/CE 初始化阶段 |

**示例**：

```
trace: DS 0x00000000 0x00000000 0x00000000 0x00000000 0x00000023 DN
```

第 5 个数据 `0x00000023` 是 `DOWNLOAD_DEBUG_FLAG`，按位拆解为：`0x00000001`（`DL_HANDSHAKE_OK`）、`0x00000002`（`DL_SEND_VER`）、`0x00000020`（`DL_PUB_KEY_VERI_FAIL`）。该组合表示 Download 已完成握手和版本交互，但 FDL 公钥校验未通过。优先核对 FDL 的 RSA 算法和签名密钥、设备当前选中的 PKH、AXDL 包是否混入旧 FDL。

由于 trace 是累积位图，应结合 AXDL 返回错误和完整串口日志判断最先失败的位置。

---

## 故障定位（续）

### Q23：SBL 安全启动失败时，如何根据串口日志定位？

SBL 负责校验 SPL 和 RTOS。先在完整串口日志中搜索下面的原文，再结合紧邻的 `Secure boot: mark ...` 判断失败对象和 slot：

| 串口日志关键字 | 表示的失败点 | 优先检查项 |
|---|---|---|
| `verify img header failed: header 0x...` | 镜像 header、magic、checksum 或读取异常，安全验签尚未开始 | 是否刷错镜像、分区内容是否完整、目标 slot 和启动介质读取是否正常 |
| `secure init failed(<ret>)` | HSM/CE 初始化失败 | HSM 固件加载和状态、镜像读取；不要先归因于 RSA 密钥错误 |
| `secure aes decrypto failed(<ret>)` | 加密镜像解密失败 | 是否把明文/密文镜像刷反，设备 Root Key/FEK 与构建 AES Key 是否匹配 |
| `secure public key verify failed(<ret>)` | 镜像 header 中的公钥未通过合法性/PKH 校验 | eFuse 选中的 PKH、RSA-2048/3072 配置、该镜像是否由对应密钥生成 |
| `secure cipher sha256 failed(<ret>)` | 镜像 SHA-256 计算失败 | HSM 状态、镜像是否完整以及存储读取是否稳定 |
| `secure cipher rsa verify failed(<ret>)` | 镜像内容的 RSA 签名验签失败 | 签名私钥与 header 公钥是否配套、RSA 位数、镜像是否在签名后被改写或损坏 |
| `secure deinit failed(<ret>)` | 安全模块释放失败 | HSM 状态；该日志本身不能直接证明镜像签名错误 |
| `Secure boot: mark spl slot:<n> partition as failed` | 当前失败对象是 SPL，`<n>` 为 slot | 检查对应 A/B slot 的 SPL 镜像和打包清单 |
| `Secure boot: mark rtos slot:<n> partition as failed` | 当前失败对象是 RTOS，`<n>` 为 slot | 检查对应 A/B slot 的 RTOS 镜像和打包清单 |

例如，若依次看到 `secure cipher rsa verify failed(...)` 和 `Secure boot: mark spl slot:1 partition as failed`，可定位为 slot B 的 SPL RSA 验签失败；这不是 BootROM 校验 SBL 失败，也不是后续 FIT 校验失败。若只在一个 slot 复现，应优先比较 A/B 分区镜像的版本、签名密钥和文件校验值。

`mark ... partition as failed` 是串口标记信息，不能假设失败状态已经持久化到存储介质。

### Q24：SPL/U-Boot 安全启动失败时，如何根据串口日志定位？

SPL 校验 FIT 中的 ATF、OP-TEE 和 U-Boot。先根据 `Checking hash(es) for Image <name>` 确认正在校验的对象，再解释后续日志：

| 串口日志关键字 | 表示的失败点 | 优先检查项 |
|---|---|---|
| `## Checking hash(es) for config <name> ...` | 开始校验 FIT 配置签名 | 继续查看紧随其后的具体错误，单独出现不是失败 |
| `## Checking hash(es) for Image <name> ...` | 开始校验 `<name>` 对应的 FIT image | 根据 `<name>` 区分 ATF、OP-TEE 或 U-Boot，继续查看后续结果 |
| `Unable to verify required signature` | required 签名缺失或未通过校验 | FIT 是否用正确私钥签名，签名节点是否为 required，SPL DTB 中是否包含匹配公钥 |
| `Verification failed` | RSA 签名值校验失败 | 签名密钥、RSA 位数、DTB 公钥、FIT 签名后是否被修改 |
| `Bad Data Hash` | FIT image 或 configuration 的 hash 不匹配 | 镜像数据是否损坏/被改写，ITS/FIT 元数据和最终打包文件是否来自同一次构建 |
| `## Decrypting Image <name> ... Error` | FIT 镜像解密失败 | 加密开关、Root Key/FEK、AES Key，以及是否混入明文镜像 |
| `Unable to load image` | 镜像读取/加载失败 | 启动介质、分区内容和 FIT 结构；这不是签名失败结论 |
| `Operation not permitted` | 校验或解密返回 `-EPERM`/`-EACCES` | 结合前面的签名、hash 或 decrypt 日志确定原因；故障类型记录为 `FAULT_ILLEGAL_IMAGE` |
| `Misc fault: <ret>` | 初始化、格式或其他未分类错误 | 保留返回值和此前第一条错误日志，不要仅凭该行判断为验签失败 |

SPL 和 U-Boot 的失败信息最终由 `board_pre_hang()` 写入故障记录。字段含义如下：

| 字段 | 含义 |
|---|---|
| `fault_id[23:0]` | 错误类型；`FAULT_ILLEGAL_IMAGE=0x2` 表示镜像非法/校验失败 |
| `fault_id[31:24]` | 当前启动阶段，如 SPL、U-Boot、Kernel |
| `fault_reason[23:0]` | 被校验的镜像，如 ATF、OP-TEE、U-Boot、Kernel、rootfs |
| `fault_reason[31:24]` | slot；0 为 slot A，1 为 slot B |

典型对应关系：
- SPL 报 ATF/OP-TEE/U-Boot 非法：检查 FIT 签名、算法和 SPL DTB 内公钥。
- U-Boot 报 Kernel 非法：同时检查签名后的 `extlinux.conf`、`Image.sign`/`Image_enc.sign` 及 U-Boot DTB 内公钥。
- U-Boot 报 rootfs 非法：检查 `rootfs_signed.img` 的 verity header、root hash 签名、分区大小和目标 slot。

当前源码路径为 `boot/uboot/u-boot-2022.10/arch/arm/mach-axera/m57/fault.c`；指南表格省略了仓库前缀 `boot/`。

### Q25：Kernel 安全启动失败时，如何根据串口日志定位？

Kernel 由 U-Boot 按 extlinux 配置加载并校验。判断时先找最早出现的错误，不要只看最后的 `hang up`：

| 串口日志关键字 | 表示的失败点 | 优先检查项 |
|---|---|---|
| `Unable to find extlinux on device (ret = <ret>).` | 未找到或无法读取 extlinux 配置 | boot 分区、文件路径、slot 和文件系统；这通常不是 RSA 验签失败 |
| `Skipping <label> for failure retrieving kernel` | Kernel 文件读取失败 | extlinux 中的 Kernel 路径、boot 分区内容和存储读取 |
| `Unable to verify required signature` | Kernel FIT required 签名缺失或未通过 | 实际加载的是否为签名 Kernel、U-Boot DTB 公钥、签名算法与密钥 |
| `Verification failed` | Kernel FIT 的 RSA 签名值校验失败 | Kernel 签名密钥与 U-Boot DTB 公钥是否配套、镜像是否被改写 |
| `Bad Data Hash` | Kernel FIT 数据或配置 hash 不匹配 | Kernel 文件完整性、签名后是否重新替换内容、打包文件是否混用 |
| `Bad Linux ARM64 Image magic!` | 解包后的 Kernel 格式或 magic 不正确 | 是否加载了错误文件或地址、镜像格式是否正确；不能仅凭该行判定 RSA 签名失败 |
| `PXE boot failed with error: 1, hang up...` | Kernel/Initrd 加载或启动参数准备失败 | 向前查找 `Skipping ...`、文件路径和读取错误；故障类型为 `FAULT_LOAD_IMAGE` |
| `PXE boot failed with error: 2, hang up...` | Kernel 已进入非法镜像/校验失败路径 | 向前查找 `Verification failed`、`Bad Data Hash` 等第一条校验错误；故障类型为 `FAULT_ILLEGAL_IMAGE` |
| `PXE boot failed with error: <>, hang up...` | extlinux 解析、内存或其他初始化类失败 | 保留负返回值和此前日志；故障类型为 `FAULT_INIT_FAILURE`，不等同于签名失败 |

例如，`Verification failed` 后出现 `PXE boot failed with error: 2, hang up...`，可定位为 U-Boot 校验 Kernel 签名失败；若只有 `Unable to find extlinux...`，则应先修复文件或分区配置，不能据此更换密钥。

### Q26：为什么更换密钥后 SBL 能过，但在 ATF/U-Boot/Kernel 处失败？

最常见原因是只替换了 `tools/imgsign` 下的 PEM，没有同步 `m57-keys.dtsi`；也可能只重编了后级镜像而未重编包含新 DTB 公钥的 SPL/U-Boot。

按以下顺序核对：

1. `SIGN_USE_RSA3072` 与实际 PEM 位数一致。
2. `m57-keys.dtsi` 更新的是对应 `key-akcipher2048` 或 `key-akcipher3072` 节点。
3. 新 SPL/U-Boot 已重新构建并进入最终包。
4. FIT 的 `algo` 和 `key-name-hint` 与 DTB 节点一致。
5. A/B 两个 slot 没有混用新旧镜像。

### Q27：为什么开启 ENABLE_CIPHER 后设备很早就无法启动？

优先检查：

1. `SECURE_BOOT` 是否同时为 `TRUE`。
2. eFuse 是否已使能固件加密；若已使能，SBL 必须是 `sbl_enc_signed.img`。
3. Root Key 是否先于 FEK 正确准备，FEK 是否对应当前构建 AES Key。
4. 包内后级组件是否也选择了 `*_enc_signed.img`，而不是明文签名镜像。
5. 是否把其他芯片生成的 FEK 或密文镜像用于当前芯片；指南建议 Root Key 每芯片唯一，因此不可默认跨芯片复用 FEK。

### Q28：为什么启用 ROOTFS_DMVERITY 时构建直接报配置错误？

当前源码主动拒绝两类组合：

- `SECURE_BOOT=FALSE` 且 `ROOTFS_DMVERITY=TRUE`。
- `ROOTFS_FS_TYPE=UBI` 且 `ROOTFS_DMVERITY=TRUE`。

将 `SECURE_BOOT` 设为 `TRUE`，并将 rootfs 改为只读 EXT4 或 SQUASH。如果产品必须使用可写 UBI，应重新评估文件系统完整性方案，而不是绕过现有组合检查。

### Q29：可以通过关闭校验或修改失败处理让板子先启动吗？

不建议。这样会掩盖密钥、镜像或 eFuse 不一致，并破坏需要验证的信任链。开发阶段应保留未锁定的测试板和可恢复下载路径，用同一组已登记密钥重新构建完整镜像，依据失败阶段逐级修复。

如果设备的 eFuse Secure Boot 已不可逆使能且没有任何匹配的签名密钥或恢复镜像，软件侧通常无法绕过 BootROM 信任根，需要按产品安全事件流程处理。

---

## 源码索引与适用边界

| 主题 | 当前源码路径 |
|---|---|
| 平台配置与组合检查 | `build/platforms/<vendor>/<platform>/config.mk` |
| 全局 RSA 密钥选择 | `build/scripts/config.mk` |
| SBL header、签名与加密 | `SafetyIsland/sbl/build/sbl/Makefile`、`build/scripts/imgsign/sbl_sign.py`、`img_aes.py` |
| SBL 校验与失败入口 | `SafetyIsland/sbl/boot/boot.c` |
| eFuse PKH/Root Key/FEK 消费 | `SafetyIsland/driver/secure/secure.c`、`secure.h` |
| FIT ITS 生成 | `build/scripts/generate_its.py` |
| SPL/U-Boot 构建与签名 | `boot/uboot/Makefile` |
| SPL/U-Boot DTB 公钥 | `boot/uboot/u-boot-2022.10/arch/arm/dts/m57-keys.dtsi` |
| Kernel FIT 与 extlinux 签名 | `kernel/linux/Makefile` |
| rootfs dm-verity 制作 | `rootfs/Makefile`、`build/scripts/imgsign/rootfs_sign.py` |
| U-Boot root hash 验证 | `boot/uboot/u-boot-2022.10/board/axera/common/m57/dm_verity.c` |
| U-Boot 故障记录 | `boot/uboot/u-boot-2022.10/arch/arm/mach-axera/m57/fault.c`、`include/fault.h` |
| AXP 镜像选择 | `build/scripts/axp_make.sh` |
