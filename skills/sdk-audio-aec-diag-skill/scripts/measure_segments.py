#!/usr/bin/env python3
"""Measure explicit sample intervals from original PCM; no inferred scene labels."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from analyze import dbfs, read_audio, read_json, validate_request


def measure(request, base, ranges):
    validate_request(request)
    if not request.get("audio") or not ranges or len(ranges) > 100:
        raise ValueError("Provide audio and 1..100 sample ranges")
    for start, end in ranges:
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError("Ranges require integer samples: 0 <= start < end (end exclusive)")
    result = {"schema_version": 1, "verification": "not_run", "audio": {}}
    for role, spec in request["audio"].items():
        _, raw, rate, samples = read_audio(base, spec)
        segments = []
        for start, end in ranges:
            if end > len(samples):
                raise ValueError("Range exceeds " + role + "; intervals are never truncated")
            chunk = samples[start:end]
            power = sum(x * x for x in chunk) / len(chunk)
            segments.append({"source": spec["path"] + f"#samples={start}:{end}",
                             "role": role, "start_sample": start, "end_sample": end, "samples": len(chunk),
                             "start_seconds": start / rate, "end_seconds": end / rate,
                             "power": power, "rms_dbfs": dbfs(math.sqrt(power)),
                             "peak_dbfs": dbfs(max(abs(x) for x in chunk)),
                             "dc_mean": sum(chunk) / len(chunk),
                             "zero_fraction": sum(x == 0 for x in chunk) / len(chunk),
                             "rail_fraction": sum(x in (-32768, 32767) for x in chunk) / len(chunk)})
        result["audio"][role] = {"path": spec["path"], "sha256": hashlib.sha256(raw).hexdigest(),
                                 "sample_rate": rate, "segments": segments}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--range", required=True, action="append", dest="ranges", metavar="START:END")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        request = args.input.resolve()
        ranges = []
        for value in args.ranges:
            start, end = value.split(":")
            ranges.append((int(start), int(end)))
        result = measure(read_json(request), request.parent, ranges)
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    print(content, end="")


if __name__ == "__main__":
    main()
