"""Bounded offline mic/ref delay measurement; NumPy is optional until requested."""
import math
import statistics


def number(value, label, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(label + " must be a finite number in [" + str(lower) + ", " + str(upper) + "]")


def validate(options):
    if not isinstance(options, dict):
        raise ValueError("delay must be an object")
    for key in ("enabled", "same_run", "shared_timebase"):
        if key in options and type(options[key]) is not bool:
            raise ValueError("delay." + key + " must be boolean")
    number(options.get("max_lag_ms", 500), "delay.max_lag_ms", 1, 2000)
    number(options.get("window_ms", 1000), "delay.window_ms", 250, 4000)
    if options.get("capture_stage", "unknown") not in ("before_compensation", "after_compensation", "unknown"):
        raise ValueError("Invalid delay.capture_stage")
    if "parameter" in options:
        param = options["parameter"]
        if not isinstance(param, dict):
            raise ValueError("delay.parameter must be an object")
        for key in ("name", "source", "semantics", "semantics_source"):
            if key in param and not isinstance(param[key], str):
                raise ValueError("delay.parameter." + key + " must be text")
        if "value_ms" in param:
            number(param["value_ms"], "delay.parameter.value_ms", -32768, 32767)
        if "tolerance_ms" in param:
            number(param["tolerance_ms"], "delay.parameter.tolerance_ms", 0, 2000)


def window_lag(np, mic, ref, start, length, limit, rate):
    """Fixed reference window vs full mic windows, with per-lag mean/energy."""
    reference = ref[start:start + length].astype(float)
    segment = mic[start - limit:start + length + limit].astype(float)
    record = {"ref_samples": [start, start + length],
              "mic_search_samples": [start - limit, start + length + limit],
              "time_seconds": start / rate, "accepted": False}
    if np.any((reference == -32768) | (reference == 32767)) or np.any((segment == -32768) | (segment == 32767)):
        record["reason"] = "digital_full_scale"
        return record
    reference -= reference.mean()
    ref_energy = float(reference @ reference)
    if ref_energy / length < (32768 * 10 ** (-60 / 20)) ** 2:
        record["reason"] = "reference_silent_or_low_energy"
        return record
    size = 1 << (len(segment) + length - 2).bit_length()
    conv = np.fft.irfft(np.fft.rfft(segment, size) * np.fft.rfft(reference[::-1], size), size)
    dot = conv[length - 1:length + 2 * limit]
    sums = np.concatenate(([0.0], np.cumsum(segment)))
    squares = np.concatenate(([0.0], np.cumsum(segment * segment)))
    local_sum = sums[length:] - sums[:-length]
    energy = np.maximum(0.0, squares[length:] - squares[:-length] - local_sum ** 2 / length)
    valid = energy / length >= (32768 * 10 ** (-60 / 20)) ** 2
    corr = np.zeros(2 * limit + 1)
    np.divide(dot, np.sqrt(energy * ref_energy), out=corr, where=valid)
    corr = np.clip(corr, -1, 1)
    score = np.abs(corr)
    index = int(np.argmax(score))
    peak = float(score[index])
    exclusion = max(1, round(rate / 1000))
    competitors = score.copy()
    competitors[max(0, index - exclusion):index + exclusion + 1] = 0
    second = float(competitors.max())
    lag = index - limit
    record.update({"candidate_lag_samples": lag, "candidate_lag_ms": 1000 * lag / rate,
                   "signed_correlation": float(corr[index]), "peak_abs_correlation": peak,
                   "competing_peak_abs_correlation": second,
                   "peak_ratio": peak / second if second > 0 else None,
                   "matched_mic_samples": [start + lag, start + lag + length]})
    if peak < .35:
        record["reason"] = "weak_correlation"
    elif abs(lag) >= limit - exclusion:
        record["reason"] = "search_boundary_peak"
    elif second > 0 and peak / second < 1.2:
        record["reason"] = "ambiguous_or_periodic"
    else:
        record.update({"accepted": True, "reason": "distinct_peak"})
    return record


def compare_parameter(result, options):
    param = options.get("parameter", {})
    comparison = {"status": "not_comparable", "reason": "A stable verified capture and documented parameter semantics are required"}
    result["parameter_comparison"] = comparison
    if result["status"] != "estimated":
        return
    meaningful = lambda x: isinstance(x, str) and x.strip().lower() not in ("", "unknown", "待确认", "未提供")
    if (param.get("semantics") != "total_ref_delay" or
            not all(meaningful(param.get(k)) for k in ("name", "source", "semantics_source")) or
            "value_ms" not in param or "tolerance_ms" not in param):
        return
    stage = options.get("capture_stage", "unknown")
    lag = result["lag_ms"]
    current = param["value_ms"]
    if current < 0 or stage == "unknown":
        comparison["reason"] = "Unknown capture stage or a special negative parameter value"
        return
    # This mapping is allowed ONLY when supplied docs describe a total pure delay on ref.
    target = lag if stage == "before_compensation" else current + lag
    if target < 0:
        comparison["reason"] = "Negative mapped target; recheck roles, time origin and parameter semantics"
        return
    excess = current - target
    margin = max(param["tolerance_ms"], result["spread_ms"], result["sample_resolution_ms"])
    comparison.update({"status": "consistent_with_measurement", "parameter": param["name"],
                       "current_ms": current, "measured_target_ms": target, "excess_ms": excess,
                       "comparison_margin_ms": margin,
                       "reason": "Conditional total-reference-delay mapping; not a validated device setting"})
    if excess > margin:
        comparison["status"] = "configured_too_large_candidate"
    elif excess < -margin:
        comparison["status"] = "configured_too_small_candidate"


def analyze_delay(request, base, audio_stats, read_audio):
    options = request.get("delay", {})
    result = {"status": "not_requested", "lag_ms": None, "lag_samples": None, "windows": [],
              "sign_convention": "positive = mic lags ref; negative = mic leads ref",
              "method": "windowed_normalized_cross_correlation_fft",
              "capture_stage": options.get("capture_stage", "unknown"),
              "thresholds": {"min_abs_correlation": .35, "min_peak_ratio": 1.2,
                             "peak_exclusion_ms": 1, "min_rms_dbfs": -60, "max_spread_ms": 2},
              "verification": "not_run"}
    if options.get("enabled") is not True:
        return result
    result["status"] = "unavailable"
    if not all(k in audio_stats for k in ("mic", "ref")):
        result["reason"] = "Valid bounded mic and ref recordings are required"
        return result
    a, b = audio_stats["mic"], audio_stats["ref"]
    result["evidence"] = [a["path"], b["path"]]
    if (a["sample_rate"], a["samples"]) != (b["sample_rate"], b["samples"]):
        result["reason"] = "Mic/ref rate or length mismatch; use a documented common interval, never independent trimming"
        return result
    rate = a["sample_rate"]
    if not 1000 <= rate <= 192000:
        result["reason"] = "Offline measurement supports rates 1000..192000; this is not an SDK capability limit"
        return result
    if request.get("scenario") in ("near_only", "double_talk", "silence"):
        result["reason"] = "Use a far-end-only segment with active reference"
        return result
    try:
        import numpy as np
    except ImportError:
        result["reason"] = "Optional NumPy dependency missing; install requirements-delay.txt to enable delay measurement"
        return result
    _, _, _, mic = read_audio(base, request["audio"]["mic"])
    _, _, _, ref = read_audio(base, request["audio"]["ref"])
    mic, ref = np.asarray(mic), np.asarray(ref)
    limit = round(options.get("max_lag_ms", 500) * rate / 1000)
    length = round(options.get("window_ms", 1000) * rate / 1000)
    count = min(5, (len(ref) - 2 * limit) // length)
    if count < 3:
        result["reason"] = "Need at least three non-overlapping reference windows plus both search margins"
        return result
    starts = np.linspace(limit, len(ref) - limit - length, count).round().astype(int)
    result["search_range_ms"] = [-1000 * limit / rate, 1000 * limit / rate]
    result["sample_resolution_ms"] = 1000 / rate
    for start in starts:
        result["windows"].append(window_lag(np, mic, ref, int(start), length, limit, rate))
    valid = [w for w in result["windows"] if w["accepted"]]
    result["accepted_windows"] = len(valid)
    if len(valid) != count:
        result.update({"status": "inconclusive", "reason": "Some windows fail energy, peak uniqueness or boundary checks; no single delay asserted"})
    else:
        lags = [w["candidate_lag_samples"] for w in valid]
        median = statistics.median(lags)
        spread = 1000 * (max(lags) - min(lags)) / rate
        result["spread_ms"] = spread
        result["file_relative_median_ms"] = median * 1000 / rate
        if spread > 2:
            result.update({"status": "unstable", "reason": "Window lag changes: inspect discontinuities, clock drift, multipath or changing signal content"})
        elif (request.get("scenario") != "far_only" or options.get("same_run") is not True or
              options.get("shared_timebase") is not True):
            result.update({"status": "provisional", "reason": "File-relative correlation only; confirm far-only, same run and common sample-zero time before physical delay claims"})
        else:
            result.update({"status": "estimated", "lag_samples": median, "lag_ms": median * 1000 / rate,
                           "reason": "Distinct peaks agree across windows; strongest correlated path, not proven first acoustic arrival"})
    compare_parameter(result, options)
    return result
