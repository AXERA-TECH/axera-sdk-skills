#!/usr/bin/env python3
"""Use ffprobe to summarize video structure and bitrate."""
import argparse
import json
import shutil
import subprocess
import sys
from statistics import median


def probe(path, sections, fmt=None, ffprobe="ffprobe"):
    command = [ffprobe, "-v", "error"]
    if fmt:
        command += ["-f", fmt]
    command += ["-select_streams", "v:0", "-show_entries", sections, "-of", "json", path]
    return json.loads(subprocess.check_output(command, text=True))


def analyze_records(stream, frames, packets):
    stream = (stream.get("streams") or [{}])[0]
    frames = frames.get("frames") or []
    packets = packets.get("packets") or []
    key_indices = [i for i, f in enumerate(frames) if str(f.get("key_frame")) == "1"]
    gops = [b - a for a, b in zip(key_indices, key_indices[1:])]
    types = {}
    sizes = {}
    for frame in frames:
        kind = frame.get("pict_type") or "unknown"
        types[kind] = types.get(kind, 0) + 1
        size = frame.get("pkt_size")
        if size is not None:
            sizes.setdefault(kind, []).append(int(size))
    total = sum(int(p.get("size", 0)) for p in packets if str(p.get("codec_type", "video")) == "video")
    times = [float(p.get("pts_time")) for p in packets if p.get("pts_time") is not None]
    duration = (max(times) - min(times)) if len(times) > 1 else None
    result = {
        "codec": stream.get("codec_name"), "profile": stream.get("profile"),
        "level": stream.get("level"), "width": stream.get("width"), "height": stream.get("height"),
        "declared_fps": stream.get("r_frame_rate"), "frame_count": len(frames),
        "frame_types": types, "gop": {"count": len(gops), "min": min(gops) if gops else None,
                                         "max": max(gops) if gops else None,
                                         "median": median(gops) if gops else None},
        "average_frame_size_bytes": {k: round(sum(v) / len(v), 2) for k, v in sizes.items()},
        "packet_bytes": total,
        "duration_seconds": round(duration, 3) if duration else None,
        "average_bitrate_kbps": round(total * 8 / duration / 1000, 2) if duration and total else None,
        "i_to_p_size_ratio": round((sum(sizes["I"]) / len(sizes["I"])) /
                                    (sum(sizes["P"]) / len(sizes["P"])), 3)
        if sizes.get("I") and sizes.get("P") else None,
        "limitations": ["ffprobe 通常不提供硬件 RC 的实际 QP、CTU QP map 或 ROI"]
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--format", help="裸码流格式，例如 h264 或 hevc")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if not shutil.which(args.ffprobe):
        raise SystemExit("未找到 ffprobe，请安装 FFmpeg 或通过 --ffprobe 指定路径")
    stream = probe(args.input, "stream=codec_name,profile,level,width,height,r_frame_rate", args.format, args.ffprobe)
    frames = probe(args.input, "frame=key_frame,pict_type,pkt_size,pts_time", args.format, args.ffprobe)
    packets = probe(args.input, "packet=codec_type,size,pts_time", args.format, args.ffprobe)
    print(json.dumps(analyze_records(stream, frames, packets), ensure_ascii=False,
                     indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
