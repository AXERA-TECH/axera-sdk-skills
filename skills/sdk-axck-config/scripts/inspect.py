"""
axck-tool inspect command
Inspects and visualizes camera-kit JSON configurations, sensors, pipeline topology, and memory pools.
Supports native camera-kit schema (sns_name, sns_attr, camera, dev_attr, ppl_config pipelines, pool.private/common)
"""
import os
import json
import glob
from typing import Dict, Any, List, Optional

def load_json(path: str) -> Optional[Any]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}

def inspect_config(config_dir: str, project: Optional[str] = None) -> Dict[str, Any]:
    resolved_dir = config_dir
    if project:
        candidate = os.path.join(config_dir, project)
        if os.path.isdir(candidate):
            resolved_dir = candidate
        else:
            candidate = os.path.join(config_dir, "service/res/config/AX615D", project)
            if os.path.isdir(candidate):
                resolved_dir = candidate

    sns_path = os.path.join(resolved_dir, "sns_info.json")
    ppl_path = os.path.join(resolved_dir, "ppl_config.json")
    app_path = os.path.join(resolved_dir, "app_config.json")

    sns_data = load_json(sns_path)
    ppl_data = load_json(ppl_path)
    app_data = load_json(app_path)

    # Check for variant files
    variants = {}
    for p in glob.glob(os.path.join(resolved_dir, "*.json")):
        base = os.path.basename(p)
        if base not in ["sns_info.json", "ppl_config.json", "app_config.json", "key_config.json", "comp_config.json", "dtcf_config.json"]:
            variants[base] = p

    report: Dict[str, Any] = {
        "config_dir": os.path.abspath(resolved_dir),
        "files_found": {
            "sns_info.json": os.path.exists(sns_path),
            "ppl_config.json": os.path.exists(ppl_path),
            "app_config.json": os.path.exists(app_path),
        },
        "variant_files_count": len(variants),
        "variants": sorted(list(variants.keys())),
        "sensors": [],
        "pipeline_summary": {},
        "memory_pools": {}
    }

    # Match camera entry in app_config to extract cam_pos, dev_id, pipe_id
    cam_info = {}
    if isinstance(app_data, dict) and "camera" in app_data:
        for c in app_data["camera"]:
            sns_name = c.get("sns_name")
            if sns_name:
                cam_info[sns_name] = c

    if isinstance(sns_data, list):
        for idx, s in enumerate(sns_data):
            sns_name = s.get("sns_name", s.get("sensor_name", "UNKNOWN"))
            attr = s.get("sns_attr", {})
            w = attr.get("width", s.get("width", 0))
            h = attr.get("height", s.get("height", 0))
            fps = attr.get("frame_rate", s.get("framerate", 0))
            settingindex = attr.get("settingindex", s.get("settingindex"))
            mipi = s.get("mipi_attr", {})
            clk = s.get("sns_clk", {})
            
            c_meta = cam_info.get(sns_name, {})
            cam_pos = c_meta.get("sns_pos", s.get("cam_pos", idx))
            dev_id = c_meta.get("dev_id", s.get("dev_id"))
            pipe_id = c_meta.get("pipe_id", s.get("pipe_id"))

            report["sensors"].append({
                "index": idx,
                "sensor_name": sns_name,
                "cam_pos": cam_pos,
                "dev_id": dev_id,
                "pipe_id": pipe_id,
                "i2c_dev": s.get("i2c_dev"),
                "i2c_addr": hex(s.get("i2c_addr", 0)) if isinstance(s.get("i2c_addr"), int) else s.get("i2c_addr"),
                "reset_gpio": s.get("reset_gpio"),
                "lanes": mipi.get("lane", s.get("lanes")),
                "mclk_id": clk.get("clk_idx", s.get("mclk_id")),
                "mclk_rate": clk.get("clk_rate"),
                "resolution": f"{w}x{h}@{fps}fps",
                "settingindex": settingindex
            })

    if isinstance(ppl_data, list):
        pipelines = []
        for p in ppl_data:
            p_type = p.get("type", "unknown")
            p_enable = p.get("enable", 0)
            ivps_list = []
            for iv in p.get("ivps", []):
                gid = iv.get("group")
                link = iv.get("link")
                in_w, in_h = 0, 0
                if iv.get("filter"):
                    in_w = iv["filter"][0].get("width", 0)
                    in_h = iv["filter"][0].get("height", 0)
                outputs = []
                for out in iv.get("output", []):
                    chnl = out.get("chnl")
                    f_list = out.get("filter", [])
                    res = ""
                    eng = ""
                    fps = 0
                    scale_tag = ""
                    if f_list:
                        f0 = f_list[0]
                        cw = f0.get('width', 0)
                        ch = f0.get('height', 0)
                        res = f"{cw}x{ch}"
                        eng = f0.get("engine", "")
                        fps = f0.get("dst_fps", 0)
                        if in_w > 0 and in_h > 0 and (cw > in_w or ch > in_h):
                            scale_tag = f" [Scale Up {round(cw/in_w, 2)}x{round(ch/in_h, 2)}]"
                    outputs.append({
                        "chnl": chnl,
                        "engine": eng,
                        "resolution": res,
                        "dst_fps": fps,
                        "scale_tag": scale_tag
                    })
                ivps_list.append({
                    "group": gid,
                    "link": link,
                    "input_res": f"{in_w}x{in_h}" if in_w and in_h else "",
                    "outputs": outputs
                })
            pipelines.append({
                "type": p_type,
                "enable": p_enable,
                "ivps": ivps_list
            })
        report["pipeline_summary"]["pipelines"] = pipelines

    if isinstance(app_data, dict):
        report["pipeline_summary"]["app_name"] = app_data.get("app_name")
        report["pipeline_summary"]["version"] = app_data.get("version")
        
        pool = app_data.get("pool", {})
        report["memory_pools"]["private"] = pool.get("private", [])
        report["memory_pools"]["common"] = pool.get("common", [])

        # VENC entries
        report["venc_count"] = len(app_data.get("venc", []))
        report["jenc_count"] = len(app_data.get("jenc", []))
        report["rtsp_count"] = len(app_data.get("rtsp", []))

    return report
