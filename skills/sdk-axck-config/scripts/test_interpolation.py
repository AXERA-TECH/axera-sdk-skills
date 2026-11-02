import os
import sys
import json
import unittest
import tempfile
import shutil

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import AxckValidator
import inspect as inspect_mod

class TestInterpolationAndPoolValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
        # Base config based on OS04D10
        self.base_sns = [{
            "sns_name": "OS04D10",
            "i2c_dev": 0,
            "i2c_addr": 0x36,
            "reset_gpio": 2,
            "sns_attr": {
                "width": 2560,
                "height": 1440,
                "frame_rate": 30.0,
                "settingindex": 0
            },
            "mipi_attr": {"lane": "lane_2"},
            "sns_clk": {"clk_idx": 0, "clk_rate": "24m"}
        }]

        self.base_ppl = [{
            "type": "front",
            "enable": 1,
            "ivps": [{
                "group": 0,
                "link": {"type": "vin", "pipe": 0, "chnl": 0},
                "filter": [{"row": 0, "col": 0, "engine": "vpp", "width": 2560, "height": 1440}],
                "output": [{
                    "chnl": 0,
                    "filter": [{"row": 1, "col": 0, "engine": "scl", "scl_type": 2, "width": 2560, "height": 1440}]
                }]
            }],
            "cache": [{
                "id": 0,
                "enc_chnl": 0,
                "vout": {"width": 2560, "height": 1440}
            }]
        }]

        self.base_app = {
            "app_name": "demo",
            "camera": [{
                "sns_name": "OS04D10",
                "sns_pos": 0,
                "dev_id": 0,
                "pipe_id": 0,
                "frame_rate": 30.0,
                "vin_ivps_mode": "AX_GW_VIN_IVPS_MODE_OFFLINE"
            }],
            "pool": {
                "private": [{"width": 2560, "height": 1440, "pixel_format": 133, "block_count": 6}],
                "common": [
                    {"width": 2560, "height": 1440, "pixel_format": 3, "block_count": 2},
                    {"width": 2560, "height": 128, "pixel_format": 3, "block_count": 1}
                ]
            }
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _write_configs(self, sns, ppl, app):
        with open(os.path.join(self.temp_dir, "sns_info.json"), "w") as f:
            json.dump(sns, f)
        with open(os.path.join(self.temp_dir, "ppl_config.json"), "w") as f:
            json.dump(ppl, f)
        with open(os.path.join(self.temp_dir, "app_config.json"), "w") as f:
            json.dump(app, f)

    def test_original_resolution_valid(self):
        self._write_configs(self.base_sns, self.base_ppl, self.base_app)
        validator = AxckValidator(config_dir=self.temp_dir)
        report = validator.run()
        self.assertTrue(report["valid"], f"Errors: {report.get('errors')}")

    def test_interpolation_missing_pool(self):
        # Scale up to 2880x1620 in IVPS and cache vout, but do not update app pool
        ppl = json.loads(json.dumps(self.base_ppl))
        ppl[0]["ivps"][0]["output"][0]["filter"][0]["width"] = 2880
        ppl[0]["ivps"][0]["output"][0]["filter"][0]["height"] = 1620
        ppl[0]["cache"][0]["vout"]["width"] = 2880
        ppl[0]["cache"][0]["vout"]["height"] = 1620

        self._write_configs(self.base_sns, ppl, self.base_app)
        validator = AxckValidator(config_dir=self.temp_dir)
        report = validator.run()

        # Should catch pool mismatch error
        error_str = " ".join(report.get("errors", []))
        self.assertTrue("2880x1620" in error_str and "pool" in error_str.lower(),
                        f"Expected error about 2880x1620 pool mismatch, got: {error_str}")

    def test_interpolation_with_correct_pool(self):
        ppl = json.loads(json.dumps(self.base_ppl))
        ppl[0]["ivps"][0]["output"][0]["filter"][0]["width"] = 2880
        ppl[0]["ivps"][0]["output"][0]["filter"][0]["height"] = 1620
        ppl[0]["cache"][0]["vout"]["width"] = 2880
        ppl[0]["cache"][0]["vout"]["height"] = 1620

        app = json.loads(json.dumps(self.base_app))
        app["pool"]["common"][0]["width"] = 2880
        app["pool"]["common"][0]["height"] = 1620
        app["pool"]["common"][1]["width"] = 2880

        self._write_configs(self.base_sns, ppl, app)
        validator = AxckValidator(config_dir=self.temp_dir)
        report = validator.run()

        self.assertTrue(report["valid"], f"Errors: {report.get('errors')}")
        # Should record an informational note about interpolation/upscale
        info_str = " ".join(report.get("info", []))
        self.assertTrue("scale" in info_str.lower() or "interpolat" in info_str.lower(),
                        f"Expected info about interpolation, got: {info_str}")

if __name__ == "__main__":
    unittest.main()
