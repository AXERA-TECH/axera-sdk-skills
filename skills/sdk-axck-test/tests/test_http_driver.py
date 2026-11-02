import unittest
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from core.http_client import AxckHttpClient, AxckResponse
from core.domain_apis import AxckClient, MediaApi, StorageApi, DtcfApi, DeviceApi, AovApi
from core.scenario import ScenarioBuilder, ScenarioRunner
from core.stress_runner import StressRunner, StressConfig

class MockCgiServer(BaseHTTPRequestHandler):
    fail_first_count = 0
    fail_target = 0

    def do_GET(self):
        # Allow simulating transient errors for retry tests
        if MockCgiServer.fail_target > 0 and MockCgiServer.fail_first_count < MockCgiServer.fail_target:
            MockCgiServer.fail_first_count += 1
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        path = self.path
        if "/cgi-bin/axnet/media_ctrl" in path:
            if "cmd=start_record" in path:
                resp = {"code": 0, "msg": "start record ok", "data": {"state": "recording"}}
            elif "cmd=stop_record" in path:
                resp = {"code": 0, "msg": "stop record ok", "data": {"state": "idle"}}
            elif "cmd=take_photo" in path:
                resp = {"code": 0, "msg": "take photo ok", "data": {"file": "/mnt/sd/photo_01.jpg"}}
            else:
                resp = {"code": -1, "msg": "unknown media cmd"}
        elif "/cgi-bin/axnet/get_storage_status" in path:
            resp = {"code": 0, "data": {"total_mb": 30000, "free_mb": 25000, "status": "mounted"}}
        elif "/cgi-bin/axnet/get_device_status" in path:
            resp = {"code": 0, "data": {"cpu_temp": 45.2, "status": "alive"}}
        elif "/cgi-bin/axnet/audio_ctrl" in path:
            if "cmd=set_mute" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_mute", "mute": 1 if "val=1" in path else 0}}
            elif "cmd=get_mute" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "get_mute", "mute": 0}}
            elif "cmd=set_vol" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_vol", "volume": 80.0}}
            elif "cmd=get_vol" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "get_vol", "volume": 80.0}}
            else:
                resp = {"code": -1, "msg": "unknown audio cmd"}
        elif "/cgi-bin/axnet/stream_ctrl" in path:
            if "cmd=set_mirror" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_mirror", "cam": 0, "mirror": 1}}
            elif "cmd=set_flip" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_flip", "cam": 0, "flip": 1}}
            elif "cmd=set_fps" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_fps", "cam": 0, "fps": 25.0}}
            elif "cmd=get_fps" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "get_fps", "cam": 0, "fps": 30.0}}
            elif "cmd=set_res" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_res", "cam": 0, "stream": 0, "w": 2560, "h": 1440}}
            elif "cmd=set_venc_type" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "set_venc_type", "cam": 0, "stream": 0, "h264": 1}}
            elif "cmd=get_stream_on" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "get_stream_on", "cam": 0, "on": 1}}
            else:
                resp = {"code": -1, "msg": "unknown stream cmd"}
        elif "/cgi-bin/axnet/rtsp_ctrl" in path:
            if "cmd=start" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "start_rtsp", "cam": 0}}
            elif "cmd=stop" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "stop_rtsp", "cam": 0}}
            else:
                resp = {"code": -1, "msg": "unknown rtsp cmd"}
        elif "/cgi-bin/axnet/storage_ctrl" in path:
            if "cmd=format" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "format", "status": "success"}}
            elif "cmd=mount" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "mount", "status": "success"}}
            elif "cmd=unmount" in path:
                resp = {"code": 0, "msg": "ok", "data": {"cmd": "unmount", "status": "success"}}
            else:
                resp = {"code": -1, "msg": "unknown storage cmd"}
        elif "/cgi-bin/axnet/switch_prev" in path:
            resp = {"code": 0, "data": {"mode": 1}}
        else:
            resp = {"code": 0, "data": "ok"}

        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format, *args):
        # Silence mock server stdout noise
        return

class TestHttpRpcDriverLayered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockCgiServer)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        MockCgiServer.fail_first_count = 0
        MockCgiServer.fail_target = 0

    def test_l0_and_l1_atomic_calls(self):
        """Scenario 1: Happy path - L0 HTTP client and L1 domain API calls."""
        client = AxckClient(host="127.0.0.1", port=self.port, timeout=2.0)
        
        # Test Media API
        res_rec = client.media.start_record()
        self.assertTrue(res_rec.success)
        self.assertEqual(res_rec.data["state"], "recording")
        self.assertGreaterEqual(res_rec.latency_ms, 0)

        res_photo = client.media.take_photo()
        self.assertTrue(res_photo.success)
        self.assertIn("photo_01.jpg", res_photo.data["file"])

        res_stop = client.media.stop_record()
        self.assertTrue(res_stop.success)

        # Test Audio API (RED -> will fail before implementation)
        res_mute = client.audio.set_mute(True)
        self.assertTrue(res_mute.success)
        self.assertEqual(res_mute.data["mute"], 1)

        res_vol = client.audio.set_volume(80.0)
        self.assertTrue(res_vol.success)

        # Test Stream API (RED -> will fail before implementation)
        res_mirror = client.stream.set_mirror(cam=0, mirror=True)
        self.assertTrue(res_mirror.success)
        self.assertEqual(res_mirror.data["mirror"], 1)

        res_res = client.stream.set_resolution(cam=0, stream=0, width=2560, height=1440)
        self.assertTrue(res_res.success)
        self.assertEqual(res_res.data["w"], 2560)

        # Test RTSP API
        res_rtsp = client.rtsp.start(cam=0)
        self.assertTrue(res_rtsp.success)

        # Test Storage API
        res_storage = client.storage.get_status()
        self.assertTrue(res_storage.success)
        self.assertEqual(res_storage.data["status"], "mounted")

        res_fmt = client.storage.format()
        self.assertTrue(res_fmt.success)

    def test_l0_transient_retry(self):
        """Scenario 2: Edge - transient failures trigger exponential backoff retry."""
        MockCgiServer.fail_target = 2  # Fail first 2 attempts with 500, succeed on 3rd
        client = AxckClient(host="127.0.0.1", port=self.port, max_retries=3, retry_delay=0.05)
        
        res = client.storage.get_status()
        self.assertTrue(res.success, f"Expected retry to succeed, got {res}")
        self.assertEqual(res.retries_attempted, 2)

    def test_l2_l3_scenario_pipeline(self):
        """Scenario 3: Scenario pipeline chaining multiple steps."""
        client = AxckClient(host="127.0.0.1", port=self.port)
        
        pipeline = (
            ScenarioBuilder("Smoke_Pipeline")
            .step("check_storage", lambda c: c.storage.get_status())
            .step("start_record", lambda c: c.media.start_record())
            .repeat("burst_capture", times=3, interval=0.01, action=lambda c: c.media.take_photo())
            .step("stop_record", lambda c: c.media.stop_record())
            .build()
        )
        
        report = ScenarioRunner(client).run(pipeline)
        self.assertTrue(report.success)
        self.assertEqual(len(report.step_results), 6) # 1 + 1 + 3 + 1
        self.assertEqual(report.failed_count, 0)

    def test_l3_stress_runner(self):
        """Scenario 4: Stress and soak engine with latency profiling."""
        client = AxckClient(host="127.0.0.1", port=self.port)
        
        config = StressConfig(
            name="photo_burst_stress",
            total_requests=20,
            concurrency=4,
            interval=0.005
        )
        
        runner = StressRunner(client)
        result = runner.run(lambda c: c.media.take_photo(), config)
        
        self.assertEqual(result.total_requests, 20)
        self.assertEqual(result.success_count, 20)
        self.assertEqual(result.failed_count, 0)
        self.assertGreater(result.p50_latency_ms, 0)
        self.assertGreaterEqual(result.p99_latency_ms, result.p50_latency_ms)

if __name__ == "__main__":
    unittest.main()
