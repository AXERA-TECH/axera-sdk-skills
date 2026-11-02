# `app_config.json` 核心字段参考

`app_config.json` 定义应用层业务逻辑与系统参数。

## 1. 核心模块与字段定义

### `camera` (摄像头阵列)
```json
{
    "sns_enable": 1,
    "sns_pos": 0,           // 0: 前摄, 1: 后摄
    "sns_id": 8,            // 对应 Sensor ID
    "sns_name": "SC438HAI",
    "frame_rate": 30,
    "pipe_id": 0,
    "dev_id": 0,
    "vin_ivps_mode": 1      // 0: AX_ITP_OFFLINE_VPP, 1: AX_GDC_ONLINE_VPP, 2: AX_ITP_ONLINE_VPP
}
```

### `pool` (CMM 内存池)
```json
{
    "private": [
        {
            "width": 2688, "height": 1520, "pixel_format": 133, "block_count": 6, "compress_mode": 2, "compress_level": 4
        }
    ],
    "common": [
        {
            "width": 2688, "height": 1520, "pixel_format": 3, "block_count": 2, "compress_mode": 2, "compress_level": 10
        }
    ]
}
```

### `venc` & `jenc` (编码器配置)
- `venc`: 数组配置 H.264/H.265 主码流与子码流的码率控制 (CBR/VBR)、QP 范围、GOP 长度。
- `jenc`: 抓拍与缩略图编码通道。

### `rtsp` (流媒体传输)
- `port_num`: RTSP 监听端口（默认 8554）。
- `stream_cnt`: 发布的码流总数。
- `stream_name`: 码流 URL 路径数组，如 `["axstream0", "axstream1"]`。

### `file` & `storage` (录像存储)
- `file_grow`: 预分配步长 (MB)。
- `file_mux`: 封装容器类型（如 `mp4`, `ts`）。
