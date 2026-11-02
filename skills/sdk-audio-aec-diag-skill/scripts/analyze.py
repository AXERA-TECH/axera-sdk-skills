#!/usr/bin/env python3
"""Measure local AEC evidence without connecting to or modifying a device."""
import argparse
import array
import hashlib
import json
import math
import re
import sys
import wave
from pathlib import Path

from proc_audio import parse_proc
from delay import analyze_delay, validate as validate_delay

MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_DURATION_SECONDS = 120
ENV_KEYS = ("soc", "board", "sdk_version", "audio_version", "os", "toolchain")


def read_json(path):
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("JSON exceeds 2 MiB")
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def positive_int(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + " must be a positive integer")
    return value


def local_file(base, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Evidence paths must be nonempty relative paths")
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError("Evidence missing or outside input directory: " + name)
    return path


def dbfs(value):
    return 20 * math.log10(value / 32768) if value > 0 else None


def read_audio(base, spec):
    if "sample_rate" in spec:
        positive_int(spec["sample_rate"], "sample_rate")
    if "channels" in spec and (type(spec["channels"]) is not int or spec["channels"] != 1):
        raise ValueError("channels must be integer 1")
    path = local_file(base, spec.get("path"))
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("Audio exceeds 32 MiB; provide a bounded segment")
    raw = path.read_bytes()
    kind = spec.get("format")
    if kind == "wav":
        with wave.open(str(path), "rb") as stream:
            if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getcomptype() != "NONE":
                raise ValueError("WAV must be uncompressed 16-bit mono")
            rate = stream.getframerate()
            positive_int(rate, "WAV rate")
            count = stream.getnframes()
            if count > rate * MAX_DURATION_SECONDS:
                raise ValueError("Audio exceeds 120 seconds")
            data = stream.readframes(count)
            if len(data) != count * 2:
                raise ValueError("Truncated WAV payload")
        if "sample_rate" in spec and spec["sample_rate"] != rate:
            raise ValueError("Declared rate disagrees with WAV header")
    elif kind == "s16le":
        rate = positive_int(spec.get("sample_rate"), "raw sample_rate")
        data = raw
    else:
        raise ValueError("format must be wav or s16le")
    if spec.get("channels", 1) != 1:
        raise ValueError("Explicitly split multichannel audio before analysis")
    if not data or len(data) % 2:
        raise ValueError("Empty or odd-length PCM payload")
    if len(data) // 2 > rate * MAX_DURATION_SECONDS:
        raise ValueError("Audio exceeds 120 seconds")
    samples = array.array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    return path, raw, rate, samples


def measure_audio(base, spec):
    path, raw, rate, samples = read_audio(base, spec)
    n = len(samples)
    power = sum(x * x for x in samples) / n
    window = max(1, rate // 100)
    frames = []
    for start in range(0, n, window):
        chunk = samples[start:start + window]
        frames.append({"start_sample": start, "samples": len(chunk),
                       "rms_dbfs": dbfs(math.sqrt(sum(x*x for x in chunk) / len(chunk)))})
    return {"path": spec["path"], "sha256": hashlib.sha256(raw).hexdigest(),
            "sample_rate": rate, "samples": n, "duration_seconds": n / rate,
            "rms_dbfs": dbfs(math.sqrt(power)), "peak_dbfs": dbfs(max(abs(x) for x in samples)),
            "dc_mean": sum(samples) / n, "zero_fraction": sum(x == 0 for x in samples) / n,
            "rail_fraction": sum(x in (-32768, 32767) for x in samples) / n,
            "power": power, "frames": frames}


def validate_request(request):
    if not isinstance(request, dict) or type(request.get("schema_version")) is not int or request["schema_version"] != 1:
        raise ValueError("Expected object with schema_version=1")
    validate_delay(request.get("delay", {}))
    for name in ("environment", "config", "capabilities", "audio", "comparison"):
        if name in request and not isinstance(request[name], dict):
            raise ValueError(name + " must be an object")
    if not isinstance(request.get("symptom", ""), str):
        raise ValueError("symptom must be text")
    if any(not isinstance(v, str) for v in request.get("environment", {}).values()):
        raise ValueError("environment values must be text")
    if request.get("integration", "unknown") not in ("integrated", "standalone", "unknown"):
        raise ValueError("Invalid integration")
    if request.get("scenario", "unknown") not in ("far_only", "near_only", "double_talk", "silence", "unknown"):
        raise ValueError("Invalid scenario")
    if "expect_aec" in request and type(request["expect_aec"]) is not bool:
        raise ValueError("expect_aec must be boolean")
    config = request.get("config", {})
    for key in ("vqe_rate", "device_rate", "output_rate", "frame_samples", "period_samples"):
        if key in config:
            positive_int(config[key], key)
    for key in ("aec_mode", "layout", "pcm_format", "source"):
        if key in config and not isinstance(config[key], str):
            raise ValueError(key + " must be text")
    caps = request.get("capabilities", {})
    for key in ("vqe_rates", "frame_samples", "pcm_formats", "layouts_without_aec"):
        if key in caps and (not isinstance(caps[key], list) or not caps[key]):
            raise ValueError("capabilities." + key + " must be a nonempty list")
    for key in ("vqe_rates", "frame_samples"):
        for value in caps.get(key, []):
            positive_int(value, key)
    for key in ("pcm_formats", "layouts_without_aec"):
        if any(not isinstance(v, str) for v in caps.get(key, [])):
            raise ValueError(key + " entries must be text")
    if "source" in caps and not isinstance(caps["source"], str):
        raise ValueError("capabilities.source must be text")
    for key in ("period_multiple_same_rate",):
        if key in caps and type(caps[key]) is not bool:
            raise ValueError(key + " must be boolean")
    for key, value in request.get("comparison", {}).items():
        if key in ("aligned", "same_run", "aec_only_unity_gain") and type(value) is not bool:
            raise ValueError("comparison flags must be boolean")
    for role, spec in request.get("audio", {}).items():
        if role not in ("mic", "ref", "output") or not isinstance(spec, dict):
            raise ValueError("audio accepts mic/ref/output objects only")
    texts = request.get("text_evidence", [])
    if not isinstance(texts, list) or len(texts) > 20:
        raise ValueError("text_evidence must be a list of at most 20 paths")


def analyze(request, base, request_name="request.json"):
    validate_request(request)
    env = request.get("environment", {})
    result = {"schema_version": 1, "status": "needs_evidence",
              "environment": {key: env.get(key) or "unknown" for key in ENV_KEYS},
              "findings": [], "missing_evidence": [], "audio": {},
              "version_evidence": [], "log_candidates": [], "proc_tables": [], "input_errors": [],
              "energy_reduction_proxy_db": None, "proxy_unavailable_reason": "Preconditions not established",
              "verification": "not_run"}
    missing = result["missing_evidence"]
    for key in ENV_KEYS:
        if result["environment"][key] == "unknown":
            missing.append("environment." + key)
    if not request.get("symptom"):
        missing.append("symptom and reproduction steps")
    config = request.get("config", {})
    caps = request.get("capabilities", {})
    supported = caps.get("source", "").strip().lower() not in ("", "unknown", "待确认", "未提供")
    if not supported:
        missing.append("capabilities.source: matching SDK public documentation")
    if not config.get("source", "").strip():
        missing.append("config.source: runtime readback or configuration evidence")
    for key in ("aec_mode", "vqe_rate", "pcm_format", "frame_samples"):
        if key not in config:
            missing.append("config." + key + ": verify runtime configuration")
    if request.get("integration") == "integrated" and "layout" not in config:
        missing.append("config.layout: match hardware reference route")
    if request.get("integration", "unknown") == "unknown":
        missing.append("integration: integrated or standalone")
    if request.get("scenario", "unknown") == "unknown":
        missing.append("scenario: far_only/near_only/double_talk/silence")

    def finding(code, category, evidence, detail, action):
        result["findings"].append({"code": code, "category": category,
                                   "evidence": evidence, "detail": detail, "next_action": action})

    if request.get("expect_aec") is True and config.get("aec_mode") == "AX_AEC_MODE_DISABLE":
        finding("AEC_DISABLED", "configuration", [request_name + "#/expect_aec", request_name + "#/config/aec_mode"],
                "Reported AEC mode is disabled despite requested AEC", "Verify runtime readback and enable a supported mode; retain old settings")
    if supported:
        for field, allowed in (("vqe_rate", "vqe_rates"), ("frame_samples", "frame_samples"), ("pcm_format", "pcm_formats")):
            if field in config and allowed in caps and config[field] not in caps[allowed]:
                finding("UNSUPPORTED_" + field.upper(), "configuration",
                        [request_name + "#/config/" + field, request_name + "#/capabilities/" + allowed, request_name + "#/capabilities/source"],
                        "Reported value is outside supplied SDK capability", "Check the cited SDK rule and correct this field only")
        if request.get("integration") == "integrated" and config.get("layout") in caps.get("layouts_without_aec", []):
            finding("LAYOUT_WITHOUT_AEC", "configuration", [request_name + "#/config/layout", request_name + "#/capabilities/layouts_without_aec"],
                    "Integrated layout does not provide the confirmed AEC path", "Confirm wiring and channel order before changing layout")
        if caps.get("period_multiple_same_rate") is True and config.get("device_rate") == config.get("vqe_rate") and all(config.get(k) for k in ("device_rate", "period_samples", "frame_samples")):
            if config["period_samples"] % config["frame_samples"]:
                finding("PERIOD_FRAME_MISMATCH", "configuration", [request_name + "#/config", request_name + "#/capabilities/period_multiple_same_rate"],
                        "Same-rate period is not a frame multiple", "Select a supported period/frame pair and verify return codes")
    for role in ("mic", "ref", "output"):
        spec = request.get("audio", {}).get(role)
        if spec is None:
            missing.append("audio." + role + ": synchronized authorized recording")
            continue
        try:
            stats = measure_audio(base, spec)
            result["audio"][role] = stats
            anchor = [stats["path"] + ":samples[0:" + str(stats["samples"]) + "]"]
            if stats["rail_fraction"] > 0:
                finding("FULL_SCALE_" + role.upper(), "signal_observation", anchor,
                        "Full-scale samples observed; not a hardware root-cause diagnosis", "Inspect waveform and compare one gain stage at a time")
            if role == "ref" and stats["zero_fraction"] == 1 and request.get("scenario") == "far_only":
                finding("REFERENCE_ZERO", "signal_observation", anchor,
                        "Provided reference is all zero during declared far-end-only speech", "Verify playback activity, reference source and channel mapping")
            if role == "output" and stats["zero_fraction"] == 1:
                finding("OUTPUT_ZERO", "signal_observation", anchor,
                        "Output silence is not proof of echo cancellation", "Check mute, near-end preservation and actual processing stage")
        except (OSError, ValueError, wave.Error, EOFError) as error:
            result["input_errors"].append({"role": role, "error": str(error)})
            missing.append("audio." + role + ": valid bounded mono PCM evidence")
    flags = request.get("comparison", {})
    mic, out = result["audio"].get("mic"), result["audio"].get("output")
    if request.get("scenario") == "far_only" and all(flags.get(k) is True for k in ("aligned", "same_run", "aec_only_unity_gain")) and mic and out:
        if (mic["sample_rate"], mic["samples"]) != (out["sample_rate"], out["samples"]):
            result["proxy_unavailable_reason"] = "Mic/output rate or length mismatch; no truncation or padding applied"
        elif mic["power"] <= 0 or out["power"] <= 0:
            result["proxy_unavailable_reason"] = "Silent input/output cannot establish useful cancellation"
        else:
            result["energy_reduction_proxy_db"] = 10 * math.log10(mic["power"] / out["power"])
            result["proxy_unavailable_reason"] = None
    for name in request.get("text_evidence", []):
        try:
            path = local_file(base, name)
            if path.stat().st_size > MAX_TEXT_BYTES:
                raise ValueError("Text exceeds 2 MiB; supply a bounded fault window")
            data = path.read_text(encoding="utf-8")
            result["proc_tables"].extend(parse_proc(data, name))
            for line_no, line in enumerate(data.splitlines(), 1):
                entry = {"path": name, "line": line_no, "text": line[:500]}
                if re.search(r"\b(version|build|sdk|ver)\b", line, re.I):
                    if len(result["version_evidence"]) < 100:
                        result["version_evidence"].append(entry)
                if re.search(r"\b(xrun|underrun|overrun|timeout|failed|error)\b|0x80[0-9a-f]{6}", line, re.I):
                    if len(result["log_candidates"]) < 100:
                        result["log_candidates"].append(entry)
        except (OSError, ValueError, UnicodeError) as error:
            result["input_errors"].append({"path": name, "error": str(error)})
    active_processors = []
    for row in result["proc_tables"]:
        if not row["section"].startswith("AI "):
            continue
        for key in ("NsEnable", "AgcEnable", "VadEnable", "NsAdvEnable"):
            if row["values"].get(key) == "1":
                active_processors.append(row["source"] + ":" + str(row["line"]) + " " + key)
        if row["section"] == "AI DEV VOLCTL ATTR":
            try:
                if float(row["values"].get("VqeVolume", "1")) != 1:
                    active_processors.append(row["source"] + ":" + str(row["line"]) + " VqeVolume")
            except ValueError:
                active_processors.append(row["source"] + ":" + str(row["line"]) + " unparsed VqeVolume")
    if active_processors and result["energy_reduction_proxy_db"] is not None:
        result["energy_reduction_proxy_db"] = None
        result["proxy_unavailable_reason"] = "AI proc reports additional processing; select and verify matching device/run before comparison"
        finding("COMPARISON_CONTEXT_CONFLICT", "capture_integrity", active_processors,
                "AEC-only assertion conflicts with supplied proc evidence",
                "Resolve processing-stage/device/run mismatch; do not label the energy ratio as ERLE")
    if mic and out and mic["sha256"] == out["sha256"]:
        finding("IDENTICAL_MIC_OUTPUT", "capture_integrity", [mic["path"], out["path"]],
                "Mic/output files are byte-identical; provenance or bypass must be checked",
                "Check capture round, file overwrite and processing stage before judging AEC")
    try:
        result["delay"] = analyze_delay(request, base, result["audio"], read_audio)
    except (OSError, ValueError, wave.Error, EOFError) as error:
        result["delay"] = {"status": "unavailable", "reason": str(error)}
        result["input_errors"].append({"role": "delay", "error": str(error)})
    timing = result["delay"]
    if timing["status"] not in ("not_requested", "estimated"):
        missing.append("delay: " + timing["reason"])
    comparison = timing.get("parameter_comparison", {})
    if comparison.get("status") in ("configured_too_large_candidate", "configured_too_small_candidate"):
        direction = "LARGE" if comparison["excess_ms"] > 0 else "SMALL"
        finding("DELAY_PARAMETER_TOO_" + direction + "_CANDIDATE", "timing",
                timing["evidence"] + [request_name + "#/delay/parameter", "measurements.json#/delay/windows"],
                "Configured total ref delay differs from measured timing under the supplied semantic mapping",
                "Verify parameter readback, SDK semantics and capture stage; change only delay within documented limits, retain old value and compare startup/single-talk/double-talk")
    if not missing and not result["input_errors"]:
        result["status"] = "measured"
    return result


def render(result):
    lines = ["# AEC measurements", "", "Status: " + result["status"],
             "Verification: not_run. Measurements are not a quality verdict.", "", "## Audio overview"]
    keys = ("path", "sample_rate", "samples", "duration_seconds", "rms_dbfs", "peak_dbfs",
            "dc_mean", "zero_fraction", "rail_fraction", "power")
    for role, stats in result["audio"].items():
        lines.append("- " + role + ": " + json.dumps(
            {key: stats[key] for key in keys}, ensure_ascii=False, allow_nan=False))
    lines.extend(["", "Full audio evidence: measurements.json#/audio/<role>; frames retain start_sample and samples.",
                  "Overview does not replace interval analysis. Null dBFS means zero energy; rail_fraction is not all distortion.",
                  "", "## Observations"])
    for item in result["findings"]:
        lines.extend(["", "- " + item["code"] + ": " + item["detail"],
                      "  Evidence: " + ", ".join(item["evidence"]), "  Next: " + item["next_action"]])
    lines.extend(["", "## Missing evidence"] + ["- " + x for x in result["missing_evidence"]])
    lines.extend(["", "## Invalid inputs"] + ["- " + json.dumps(x, ensure_ascii=False) for x in result["input_errors"]])
    lines.extend(["", "## Energy reduction proxy", str(result["energy_reduction_proxy_db"]),
                  str(result["proxy_unavailable_reason"]), "", "See measurements.json for audio metrics and log line anchors."])
    timing = result.get("delay", {})
    lines.extend(["", "## Mic/ref delay", "Status: " + timing.get("status", "unavailable"),
                  "Positive = mic lags ref; negative = mic leads ref.",
                  "Estimated lag (ms): " + str(timing.get("lag_ms")), timing.get("reason", ""),
                  "Parameter comparison: " + json.dumps(timing.get("parameter_comparison", {}), ensure_ascii=False)])
    for window in timing.get("windows", []):
        lines.append("- " + json.dumps(window, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("Output already exists; choose a new directory")
        result = analyze(read_json(args.input), args.input.resolve().parent, args.input.name)
        result["request_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "measurements.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (args.out / "measurements.md").write_text(render(result), encoding="utf-8")
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
