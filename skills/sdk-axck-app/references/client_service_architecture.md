# AXCK Client-Service Architecture & RPC Protocol

AX615 camera-kit 采用 Client-Service 分离架构：
- **Service (`axck_service`)**: 作为后台守护进程运行，独占掌控硬件底层（VIN, ISP, IVPS, VENC, JENC, VO, POOL, ALGO），通过 nanomsg RPC 监听并执行应用层指令。
- **Client (`libaxck_client.so`)**: 应用层动态链接库（支持 C/C++），供上层应用（如 LVGL UI、RTSP 服务端、Web 服务端、CLI 测试程序）调用。

## 1. 核心头文件索引
| 头文件 | 作用说明 |
|---|---|
| `axck_api.h` | 顶层初始化与生命周期：`AXCK_Init()`, `AXCK_DeInit()` |
| `axck_media_api.h` | 视频流、音频流、抓拍、回放控制：`AXCK_MEDIA_StartRecord()`, `AXCK_MEDIA_TakePhoto()` |
| `axck_device_api.h` | 摄像头控制、分辨率切换、曝光与夜视：`AXCK_DEV_SetCameraAttr()`, `AXCK_DEV_SwitchSensor()` |
| `axck_storage_api.h`| SD 卡存储、循环录像、紧急视频保护与格式化 |
| `axck_dtcf_api.h`   | 录像文件目录规范与检索协议 |

## 2. 进程通信 (IPC) 协议
- 通信机制：基于 `nanomsg` 的 Pair / Req-Rep 机制。
- IPC Endpoint：通过本地 IPC 套接字或内部 IPC 端口连接。
- 启动顺序：
  1. 系统引导后启动 `axck_service`（加载 `/param/axck/res/config/` 或 `res/config/` 下的 JSON 配置）。
  2. `axck_service` 初始化底层多媒体系统并就绪。
  3. 客户端进程调用 `AXCK_Init()` 与 Service 建立握手连接。

## 3. 测试工具 `axck_test` 操作指南
`camera-kit/apps/test/` 提供了完整的交互式测试控制台：
```bash
./axck_test
```
常用指令集：
- `1`: 开始录像 (`Test_StartRecord`)
- `2`: 停止录像 (`Test_StopRecord`)
- `3`: 触发抓拍 (`OnStartPhoto` / `OnTakePhoto`)
- `4`: 切换前摄预览 (`OnSwitchFrontPreview`)
- `5`: 切换后摄预览 (`OnSwitchBackPreview`)
- `6`: 四分割预览 (`OnSwitchQuadPreview`)
- `7`: 切换码流分辨率 (`OnSetFrontCamStream`)
