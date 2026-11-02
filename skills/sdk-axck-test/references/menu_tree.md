# axck_test 多级菜单树与选项参考

`axck_test` 是 camera-kit 提供的板端命令行交互式测试套件，默认支持四个核心子系统菜单。

> **核心原则**：
> 1. 所有子菜单返回上级主菜单的选项均为 **`0. Back.`**（不是 `q`）。
> 2. 主菜单中的 `0` 代表 **`0. Exit test.`**（退出测试程序至 Shell）。

---

## 1. 主菜单 (Main Menu - "Options:")
- `0`: Exit test. (退出测试程序返回系统 Shell)
- `1`: Media api test. (进入多媒体流、录像、抓拍、音频、RTSP 菜单)
- `2`: Storage api test. (进入存储与 SD 卡测试菜单)
- `3`: Dtcf api test. (进入文件系统目录与 DTCF 规范测试菜单)
- `4`: Device api test. (进入设备自检与硬件状态菜单)

---

## 2. Media api options (子菜单 1)
- `0`: Back. (返回上级主菜单)
- `1`: Set front stream on/off. (前后摄开流与关流)
- `2`: Get front FPS. (获取当前实时推流/显示帧率)
- `3`: Update front osd display. (时间水印与文字 OSD 叠加)
- `4`: Update front sns mode. (SDR / HDR 模式动态切换)
- `5`: Update front mirror. (水平镜像使能与关闭)
- `6`: Update front flip. (垂直翻转使能与关闭)
- `7`: Update front main stream resolution. (主码流分辨率切换：0: 2560x1440, 1: 1920x1080, 2: 1280x720)
- `8`: Update front sub stream resolution. (子码流分辨率切换)
- `9`: Start record. (启动 MP4 循环录像)
- `10`: Stop record. (停止 MP4 录像并封包写盘)
- `11`: Set front venc type(main stream). (H.264 / H.265 编码格式切换，**注意：会触发 Pipeline 销毁重建**)
- `12`: Set record time. (修改分段录像时长，如 1 分钟 / 3 分钟)
- `13`: Start urgent video(precondition: start record). (触发加锁紧急录像)
- `14`: Start AOV. (启动 AOV 低功耗监控)
- `15`: Stop AOV. (停止 AOV)
- `16`: Pause AOV sleep.
- `17`: Resume AOV sleep.
- `18`: Set AIn mute. (音频输入静音)
- `19`: Set AIn unmute. (音频输入取消静音)
- `20`: Get AIn mute. (查询静音状态)
- `21`: Get media status. (查询媒体服务运行状态)
- `22`: System sleep. (系统休眠)
- `23`: System sleep with restarting PPL.
- `24`: System deep sleep. (系统深度休眠)
- `25`: System deep sleep with restarting PPL.
- `26`: Start RTSP. (启动 RTSP 实时推流)
- `27`: Stop RTSP. (停止 RTSP 服务)
- `28`: Capture image. (JENC JPEG 单帧抓拍，默认落盘至 /mnt/tfcard/Photo/F/)
- `29`: Play sound. (播放本地音频 /opt/data/audio.aac)
- `30`: Stop sound. (停止音频播放)
- `31`: Play video. (视频回放测试)
- `32`: Set AOut volume. (设置输出音量)

---

## 3. Storage api options (子菜单 2)
- `0`: Back. (返回上级主菜单)
- `1`: Get storage status. (查询 TF 卡挂载与可用状态)
- `2`: Get SDCard total size. (查询 SD 卡总容量)
- `3`: Get SDCard free size. (查询 SD 卡剩余可用空间)
- `4`: Format SDCard. (格式化 SD 卡)
- `5`: Hotplug SDCard. (模拟热插拔事件)
- `6`: Auto remove. (自动循环覆盖清理配置)

---

## 4. Dtcf api options (子菜单 3)
- `0`: Back. (返回上级主菜单)
- `1`: Dump dtcf info. (导出 DTCF 目录树与节点信息)
- `2`: Set file format. (配置抓拍/录像文件命名格式)
- `3`: Update emergency partition. (更新紧急分区配额)
- `4`: Get file list. (获取多媒体文件列表)
- `5`: Delete old file. (触发老文件淘汰清理)

---

## 5. Device api options (子菜单 4)
- `0`: Back. (返回上级主菜单)
- `1`: Reboot. (**严禁在常规用例中直接调用**，会导致单板重启断联)
- `2`: Reset factory. (恢复出厂设置)
- `3`: Query all info. (查询芯片型号、固件版本、SN、MAC 信息)
- `4`: Query all status. (查询设备各子模块运行健康状态)

