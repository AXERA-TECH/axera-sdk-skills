import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_bitstream import analyze_records


class AnalyzeBitstreamTest(unittest.TestCase):
    def test_gop_and_ip_ratio(self):
        stream = {"streams": [{"codec_name": "h264", "width": 1280, "height": 720,
                               "r_frame_rate": "30/1"}]}
        frames = {"frames": [
            {"key_frame": 1, "pict_type": "I", "pkt_size": "1000", "pts_time": "0"},
            {"key_frame": 0, "pict_type": "P", "pkt_size": "500", "pts_time": "0.033"},
            {"key_frame": 1, "pict_type": "I", "pkt_size": "1200", "pts_time": "0.066"},
        ]}
        packets = {"packets": [
            {"codec_type": "video", "size": "1000", "pts_time": "0"},
            {"codec_type": "video", "size": "500", "pts_time": "0.033"},
            {"codec_type": "video", "size": "1200", "pts_time": "0.066"},
        ]}
        result = analyze_records(stream, frames, packets)
        self.assertEqual(result["gop"]["median"], 2)
        self.assertAlmostEqual(result["i_to_p_size_ratio"], 2.2)


if __name__ == "__main__":
    unittest.main()
