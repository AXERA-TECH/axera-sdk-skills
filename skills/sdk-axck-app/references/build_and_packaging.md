# AX615 Camera-Kit 编译与固件打包指南 (Build and Packaging)

本文档详细指导 AX615 camera-kit 各模块的编译流程、环境变量、子目录依赖以及如何通过 `opt.filelist` 组装固件镜像。

---

## 1. 编译系统架构与依赖拓扑

camera-kit 位于 SDK 顶层根目录下的 `camera-kit/` 目录中，其顶层 `Makefile` 管理 5 个核心子模块：

```
camera-kit/Makefile
       │
       ├── 1. 3rd/      (第三方基础库: nanomsg, cJSON, libexif, live555, iniparser)
       ├── 2. com/      (公共工具与中间层: 基础工具类, 内存共享工具)
       ├── 3. service/  (后台守护进程: axck_service 核心多媒体服务)
       ├── 4. client/   (客户端 SDK: libaxck_client.so 动态链接库)
       └── 5. apps/     (上层应用: axck_test 命令行测试工具, dvcam LVGL 应用)
```

### 关键编译顺序（不可颠倒）：
必须严格按照 `3rd -> com -> service -> client -> apps` 的顺序串行编译（`SUBDIRS -j1`），因为：
- `service` 依赖 `3rd` 的 nanomsg 和 `com` 的公共数据类型；
- `client` 依赖 `3rd` 的 IPC 协议和 `service` 导出的 RPC 消息格式；
- `apps`（如 `axck_test`）依赖 `client` 生成的 `libaxck_client.so`。

---

## 2. 编译环境变量与准备

camera-kit 依赖上层 `build/config.mak` 与目标工程配置（如 `PROJECT=AX615_dashcam_nor`）：

```bash
# 进入 SDK 根目录
cd <AX615_SDK_ROOT>  # 如 $HOME/ax615_trunk 或工程目录

# 设置工程目标（例如 AX615 dashcam nor 方案）
export PROJECT=AX615_dashcam_nor
```

---

## 3. 常用编译命令

### 3.1 全量编译 camera-kit
在 `camera-kit/` 目录下：
```bash
cd camera-kit
make all          # 编译所有模块
make install      # 将产物安装至 camera-kit/out/$(MSP_OUT_DIR)
```

### 3.2 独立编译/单模块编译
若仅修改了应用层或测试用例，无需重编整个底层：
```bash
# 单独编译 apps/test (生成 axck_test)
make -C apps/test

# 单独编译 apps/dvcam (生成 UI 应用)
make -C apps/dvcam

# 单独编译 client (重新生成 libaxck_client.so)
make -C client

# 单独编译 service (重新生成 axck_service)
make -C service
```

### 3.3 清理构建产物
```bash
make clean        # 清理所有中间目标文件与 out 目录
```

---

## 4. 输出目录产物结构 (`out/$(MSP_OUT_DIR)`)

执行 `make install` 后，产物归档于 `camera-kit/out/$(MSP_OUT_DIR)/`：
- `bin/axck_service`：多媒体核心服务进程
- `bin/axck_test`：交互式命令行测试程序
- `lib/libaxck_client.so`：应用层客户端动态库
- `third-party/lib/`：第三方依赖动态库（如 `libnanomsg.so`, `libexif.so`）
- `bin/res/config/AX615D/<project>/`：配置文件部署镜像目录

---

## 5. 固件镜像打包机制 (`opt.filelist`)

SDK 打包系统通过 `build/projects/$(PROJECT)/opt.filelist` 声明拷贝规则，将编译生成的二进制与资源文件打包进入目标根文件系统（RootFS）：

```text
# camera-kit 相关的打包规则示例：
@dir: camera-kit/out/$(MSP_OUT_DIR)
lib/libaxck*.so lib/

@dir: camera-kit/out/$(MSP_OUT_DIR)
third-party/lib/libexif* usr/lib/

@dir: camera-kit/out/$(MSP_OUT_DIR)
bin/axck_service
bin/axck_test

# 将选定工程的配置文件打包到固件的 bin/res/config/
bin/res/config/AX615D/demo/* bin/res/config/

bin/res/osd/* bin/res/osd/
```

### ⚠️ 打包与发布注意事项：
1. **配置文件生效路径**：`opt.filelist` 将 `AX615D/demo/*` 扁平拷贝到固件的 `bin/res/config/`。运行时若要测试新 Sensor 变体（如 `sns_info_sc431hai.json`），请确保 `sns_info.json` 指向正确的软链接或直接覆盖主文件后再打包。
2. **符号表与体积限制**：NOR Flash 容量通常受限（如 16MB/32MB），确保发布时二进制文件经过 strip 处理。
