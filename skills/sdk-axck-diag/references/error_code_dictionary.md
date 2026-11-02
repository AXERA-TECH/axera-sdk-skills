# AXERA SDK 错误码解码字典

## VIN 模块 (0x8002xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80020005 | AX_ERR_VIN_ILLEGAL_PARAM | VIN dev 或 pipe 参数非法 | 检查 sns_info.json 的 dev_attr、mipi_intf_attr、lane 配置 |
| 0x80020012 | AX_ERR_VIN_NOT_PERM | VIN 操作在当前状态不允许 | 确认初始化顺序：先创建 DEV 再创建 PIPE |

## ISP 模块 (0x8003xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80030005 | AX_ERR_ISP_ILLEGAL_PARAM | ISP pipeline 参数非法 | 检查 pipe_attr 的 width/height 与 sns_attr 一致性 |

## POOL/CMM 模块 (0x8005xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80050003 | AX_ERR_POOL_ILLEGAL_PARAM | 内存池创建参数错误 | 检查 block_size 和 block_count 合理性 |
| 0x80050004 | AX_ERR_POOL_NOBUF | CMM 内存池耗尽 | 增加 block_count 或降低分辨率；检查 buffer 泄漏 |

## VENC 模块 (0x8007xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80070201 | AX_ERR_VENC_NULL_PTR | VENC API 空指针 | 检查编码通道创建参数 |
| 0x80070203 | AX_ERR_VENC_ILLEGAL_PARAM | AX_VENC_CreateChn 参数非法 | 检查 venc 的 width、height、framerate、bitrate |
| 0x80070216 | AX_ERR_VENC_EXIST | VENC/JENC 通道已存在或冲突 | 检查 enc_chnl 通道号，VENC 和 JENC 共享 0~15 |

## IVPS 模块 (0x8008xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80080004 | AX_ERR_IVPS_UNEXIST | IVPS group/channel 不存在 | 检查 pipeline 启动顺序 |
| 0x80080005 | AX_ERR_IVPS_ILLEGAL_PARAM | IVPS 属性参数非法 | 确保 filter 尺寸偶数对齐 |

## SYS 模块 (0x8001xxxx)

| 错误码 | 名称 | 原因 | 排查方向 |
|--------|------|------|---------|
| 0x80010005 | AX_ERR_SYS_ILLEGAL_PARAM | 系统级参数非法 | 检查 AX_SYS_Init / AX_SYS_Link 参数 |

## 错误码命名规律

AXERA 错误码格式：`0x800MXXXX`
- `M` = 模块编号（01=SYS, 02=VIN, 03=ISP, 05=POOL, 07=VENC, 08=IVPS）
- `XXXX` = 具体错误子码
