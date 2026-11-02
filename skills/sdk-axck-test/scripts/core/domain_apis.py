#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/domain_apis.py
L1: 领域原子 API 层 (Domain Atomic API Layer)
将板端 axck_service CGI 映射为高内聚、独立的 Pythonic 领域对象与调用方法。
"""

from typing import Optional, Dict, Any, List
from .http_client import AxckHttpClient, AxckResponse

class MediaApi:
    """媒体子系统控制 API (录像、拍照、流媒体、紧急录像)"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def start_record(self) -> AxckResponse:
        """开始普通录像"""
        return self._c.request("/cgi-bin/axnet/media_ctrl", params={"cmd": "start_record"})

    def stop_record(self) -> AxckResponse:
        """停止录像"""
        return self._c.request("/cgi-bin/axnet/media_ctrl", params={"cmd": "stop_record"})

    def take_photo(self, cam: int = -1) -> AxckResponse:
        """单张抓拍/拍照 (cam: -1 为全摄抓拍, 0: 前摄, 1: 后摄)"""
        params = {"cmd": "take_photo"}
        if cam != -1:
            params["cam"] = cam
        return self._c.request("/cgi-bin/axnet/media_ctrl", params=params)

    def start_urgent(self) -> AxckResponse:
        """触发紧急加锁录像"""
        return self._c.request("/cgi-bin/axnet/media_ctrl", params={"cmd": "start_urgent"})

    def switch_prev(self, mode: int = 1) -> AxckResponse:
        """切换预览通道 (0: 关, 1: 主摄, 2: 辅摄, 3: 双摄并排)"""
        return self._c.request("/cgi-bin/axnet/switch_prev", params={"mode": mode})

class StorageApi:
    """存储子系统控制 API (SD 卡容量、挂载状态、格式化)"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def get_status(self) -> AxckResponse:
        """查询 SD 卡容量与状态"""
        return self._c.request("/cgi-bin/axnet/get_storage_status")

    def format(self) -> AxckResponse:
        """格式化 SD 卡"""
        return self._c.request("/cgi-bin/axnet/storage_ctrl", params={"cmd": "format"})

    def mount(self, create_default: bool = True) -> AxckResponse:
        """挂载 SD 卡"""
        return self._c.request("/cgi-bin/axnet/storage_ctrl", params={"cmd": "mount", "val": 1 if create_default else 0})

    def unmount(self, clean_db: bool = False) -> AxckResponse:
        """卸载 SD 卡"""
        return self._c.request("/cgi-bin/axnet/storage_ctrl", params={"cmd": "unmount", "val": 1 if clean_db else 0})

class AudioApi:
    """音频输入输出控制 API"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def set_mute(self, mute: bool) -> AxckResponse:
        """设置音频输入静音/解静音"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "set_mute", "val": 1 if mute else 0})

    def get_mute(self) -> AxckResponse:
        """获取音频输入静音状态"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "get_mute"})

    def set_volume(self, volume: float) -> AxckResponse:
        """设置音频输出音量 (0.0 ~ 100.0)"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "set_vol", "val": volume})

    def get_volume(self) -> AxckResponse:
        """获取音频输出音量"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "get_vol"})

    def play_sound(self, filepath: str) -> AxckResponse:
        """播放音频提示音"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "play_sound", "file": filepath})

    def stop_sound(self) -> AxckResponse:
        """停止播放提示音"""
        return self._c.request("/cgi-bin/axnet/audio_ctrl", params={"cmd": "stop_sound"})

class StreamApi:
    """码流、画质与视频拓扑控制 API"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def set_stream_on(self, cam: int = 0, on: bool = True) -> AxckResponse:
        """开流/关流"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "set_stream_on", "cam": cam, "val": 1 if on else 0})

    def get_stream_on(self, cam: int = 0) -> AxckResponse:
        """获取开流状态"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "get_stream_on", "cam": cam})

    def set_mirror(self, cam: int = 0, mirror: bool = True) -> AxckResponse:
        """水平镜像设置"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "set_mirror", "cam": cam, "val": 1 if mirror else 0})

    def set_flip(self, cam: int = 0, flip: bool = True) -> AxckResponse:
        """垂直翻转设置"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "set_flip", "cam": cam, "val": 1 if flip else 0})

    def set_fps(self, cam: int = 0, fps: float = 30.0) -> AxckResponse:
        """动态设置帧率"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "set_fps", "cam": cam, "val": fps})

    def get_fps(self, cam: int = 0) -> AxckResponse:
        """获取当前配置帧率"""
        return self._c.request("/cgi-bin/axnet/stream_ctrl", params={"cmd": "get_fps", "cam": cam})

    def set_resolution(self, cam: int = 0, stream: int = 0, width: int = 2560, height: int = 1440) -> AxckResponse:
        """动态调整主/辅码流分辨率"""
        return self._c.request(
            "/cgi-bin/axnet/stream_ctrl",
            params={"cmd": "set_res", "cam": cam, "stream": stream, "w": width, "h": height}
        )

    def set_venc_type(self, cam: int = 0, stream: int = 0, is_h264: bool = True, timeout: float = 15.0) -> AxckResponse:
        """切换编码格式 (0: H.264, 1: H.265)

        断流切换操作：底层执行 PPL Stop/Start 管线重建，实测耗时约 8~10s，
        默认 timeout=15s 留出充足余量。
        """
        return self._c.request(
            "/cgi-bin/axnet/stream_ctrl",
            params={"cmd": "set_venc_type", "cam": cam, "stream": stream, "val": 0 if is_h264 else 1},
            timeout=timeout,
        )

    def set_record_time(self, cam: int = 0, stream: int = 0, sec: int = 60) -> AxckResponse:
        """设置分段录像时长 (秒)"""
        return self._c.request(
            "/cgi-bin/axnet/stream_ctrl",
            params={"cmd": "set_rec_time", "cam": cam, "stream": stream, "val": sec}
        )

class RtspApi:
    """RTSP 实时流媒体服务控制 API"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def start(self, cam: int = 0) -> AxckResponse:
        """启动指定摄像头的 RTSP 推流服务器 (默认 8554 端口)"""
        return self._c.request("/cgi-bin/axnet/rtsp_ctrl", params={"cmd": "start_rtsp", "cam": cam})

    def stop(self, cam: int = 0) -> AxckResponse:
        """停止 RTSP 服务器"""
        return self._c.request("/cgi-bin/axnet/rtsp_ctrl", params={"cmd": "stop_rtsp", "cam": cam})

    # 别名兼容
    def start_rtsp(self, cam: int = 0) -> AxckResponse:
        return self.start(cam)

    def stop_rtsp(self, cam: int = 0) -> AxckResponse:
        return self.stop(cam)

class DtcfApi:
    """DTCF 媒体资产管理 API (查询文件列表、缩略图、分片回放)"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def get_file_count(self, file_type: int = 0) -> AxckResponse:
        """查询媒体文件计数"""
        return self._c.request("/cgi-bin/axnet/get_file_count", params={"type": file_type})

    def get_file_list(self, file_type: int = 0, start_idx: int = 0, count: int = 20) -> AxckResponse:
        """分页获取文件列表"""
        return self._c.request(
            "/cgi-bin/axnet/get_file_list",
            params={"type": file_type, "start": start_idx, "count": count}
        )

    def get_file_thumb(self, filename: str) -> AxckResponse:
        """获取视频/照片缩略图数据"""
        return self._c.request("/cgi-bin/axnet/get_file_thumb", params={"name": filename})

    def get_file_play(self, filename: str, offset: int = 0) -> AxckResponse:
        """请求视频切片回放流"""
        return self._c.request("/cgi-bin/axnet/get_file_play", params={"name": filename, "offset": offset})

class DeviceApi:
    """设备全局状态与能力查询 API"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def get_status(self) -> AxckResponse:
        """获取设备综合状态 (CPU/温度/运行时间等)"""
        return self._c.request("/cgi-bin/axnet/get_device_status")

class AovApi:
    """AOV 超低功耗休眠唤醒控制 API"""
    def __init__(self, client: AxckHttpClient):
        self._c = client

    def control(self, action: str = "start") -> AxckResponse:
        """
        控制 AOV 状态: start, stop, pause, resume
        """
        return self._c.request("/cgi-bin/axnet/aov_ctrl", params={"cmd": action})

class AxckClient:
    """
    统一 Facade 客户端聚合入口
    """
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 80,
        timeout: float = 5.0,
        max_retries: int = 0,
        retry_delay: float = 0.1
    ):
        self.http = AxckHttpClient(
            host=host,
            port=port,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay
        )
        self.media = MediaApi(self.http)
        self.audio = AudioApi(self.http)
        self.stream = StreamApi(self.http)
        self.rtsp = RtspApi(self.http)
        self.storage = StorageApi(self.http)
        self.dtcf = DtcfApi(self.http)
        self.device = DeviceApi(self.http)
        self.aov = AovApi(self.http)
