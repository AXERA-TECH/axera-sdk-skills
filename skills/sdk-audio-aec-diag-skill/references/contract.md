# 工具使用与输入输出格式

字段/单位核对时读第二节；音频测量、结构化交付或 Eval 时按需读取全文。普通问答和单份 Markdown 报告直接按主流程完成。

## 一、运行方法

需要 Python 3.10+；时延测量另需 NumPy，允许安装依赖时运行 `python3 -m pip install -r "<skill-dir>/scripts/requirements-delay.txt"`。

证据、请求与结果保存在 skill 目录外。`<skill-dir>` 为 SKILL.md 所在目录，输出目录尚不存在。Bash 示例：

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 "<skill-dir>/scripts/analyze.py" --input "<request.json>" --out "<new-out>"
```

先检查 measurements.json 的 input_errors、missing_evidence 和各项出处，再解释音频统计与时延。measured 只说明测量输入齐备，不表示问题已解决；依赖缺失如实保留 unavailable。日志关键词只索引位置，含义以原文为准。

### 大测量结果的读取

先读脚本生成的 measurements.md，其中包含各路音频概况（原路径、采样率、样本数、时长、RMS/峰值、DC、全零比例、满幅比例、power）、发现、缺项、输入错误、时延状态、参数可比性和全部时延窗口。完整 JSON 保留在磁盘，使用 Python 按字段读取分段数据及原始证据，避免把整份文件输出到对话。核对概况或读取旧版测量文件时可使用以下示例：

```python
import json
from pathlib import Path

name = "out/measurements.json"
data = json.loads(Path(name).read_text())
keys = ("samples", "sample_rate", "rms_dbfs", "peak_dbfs", "power", "zero_fraction", "rail_fraction")
print(name, json.dumps({role: {key: audio.get(key) for key in keys}
                       for role, audio in data["audio"].items()}, ensure_ascii=False))
```

路径按实际轮次选择。单轮请求准备好后只测量一次；多轮请求可在一次 Shell 调用中依次测量，主轮先输出，避免子目录提前创建导致主轮拒绝覆盖。概况不能代替分段分析；启动、恢复或切换问题还需读取相应区间指标，保留轮次、窗口位置、有效性及拒绝原因。多轮 sample 0 的应用时刻分别按采集说明映射；出现矛盾时回查原始日志与 JSON 定位。输入和参数未变、结果有效时复用测量；输入错误或需要改变测量参数时另存新结果。

分段比较使用 `audio.<role>.frames` 的 `start_sample`、`samples` 和 `sample_rate` 定位，不改变窗口大小或搜索范围来缩短运行。RMS 合并需按样本数加权在线性能量域计算，不能直接平均 dB；边界落在帧内时按原始 PCM 精确取段。短时吞音、首字丢失保留局部帧与共同时间关系，不能只比较整段均值。

### 原始 PCM 分段统计

需要按场景或局部区间比较时，使用随包工具一次计算多段，避免临时编写统计程序：

```bash
python3 "<skill-dir>/scripts/measure_segments.py" --input "<request.json>" --range 0:16000 --range 16000:32000 --out "<new-segments.json>"
```

区间为 `[start_sample, end_sample)`，示例代表 16 kHz 下前两秒，实际边界由采集说明与录音确定。工具直接读取 request 中原始 PCM，按样本计算能量、RMS、峰值、DC、全零与满幅比例；不会对齐不同轮次、猜测场景或输出 ERLE。结果保留原始文件 SHA256、采样率和区间，打印到终端并保存新文件。跨采样率按各自时间关系另建请求；相同内容按片段内相对位置比较，长度不等不自动截断。首字/吞音先查看已有 10 ms 帧定位，再传入局部范围精确统计；场景均值不替代局部证据。此工具不替代 analyze.py 的全录音统计或时延测量。

每段结果中的 source 是原始 PCM 的 `[start_sample, end_sample)` 引用，role 表示 mic/ref/output。写 diagnosis.evidence 时沿用该原始引用，在 observation 中写明处理前 MIC/参考 REF/处理后 output、轮次、场景和实测指标，并可补充统计 JSON 的定位。输入和输出分别记录，避免把对照一侧的观察只放入未被引用的汇总文件。

## 二、request.json

UTF-8 JSON，schema_version=1；最小请求为 `{"schema_version":1}`。其余只填已知事实，禁止用默认能力或虚构 PCM 补齐材料。

| 字段 | 内容 |
|---|---|
| symptom | 现象、回声方向、复现条件的字符串 |
| environment | soc / board / sdk_version / audio_version / os / toolchain，字符串 |
| integration | integrated / standalone / unknown |
| scenario | far_only / near_only / double_talk / silence / unknown |
| expect_aec | 布尔值，缺失不猜 |
| config | aec_mode、layout、pcm_format、source 为字符串；vqe_rate/device_rate/output_rate/frame_samples/period_samples 为正整数 |
| capabilities | 对外依据 source；vqe_rates/frame_samples 为正整数列表，pcm_formats/layouts_without_aec 为字符串列表，period_multiple_same_rate 为布尔值；无来源不强制能力限制 |
| audio | mic/ref/output 各含 path、format=wav 或 s16le、sample_rate、channels=1；raw 必填 rate，WAV 从头读取并可校对 |
| text_evidence | 请求目录内日志/proc 的相对路径列表，最多 20 个 |
| comparison | aligned / same_run / aec_only_unity_gain，只有已确认才填 true |
| delay | 按下节填写，测量前提及结果解释见 [delay.md](delay.md)；与 comparison.aligned 无关 |

### 从现场材料整理字段

config 是工具字段，不直接写进 SDK。先选定设备和轮次，配置文件、API 读回和 proc 有冲突时保留各自出处，不能悄悄合成一个“正确配置”。以下映射依据《AX AUDIO API 文档》V1.7（2026/07/13）§3、§5，使用前核对版本：

| 公开属性 / proc 字段 | 工具字段 | 填写条件 |
|---|---|---|
| VQE `s32SampleRate/u32FrameSamples` 或 `SampleRate/FrameSamples` | `config.vqe_rate/frame_samples` | 取目标 AI 的算法阶段 |
| AI `enSamplerate/u32PeriodSize` 或 `Samplerate/PeriodSize` | `config.device_rate/period_samples` | 取设备阶段，原文 `PeroidSize/u32PeroidSize` 拼写变体另注明 |
| `AecMode` | `config.aec_mode` | 该版 0/1/2 分别整理为 `AX_AEC_MODE_DISABLE/AX_AEC_MODE_FLOAT/AX_AEC_MODE_FIXED` |
| `LayoutMode` | `config.layout` | 按 [diagnosis.md](diagnosis.md) 的布局枚举转换，不把数字字符串直接当枚举名 |
| 目标输出的重采样信息及录音格式 | `config.output_rate`、`audio.*.sample_rate` | 分阶段取值，不能把 AO 的输出率直接用于 AI 录音 |
| 位宽、实际文件编码及声道信息 | `config.pcm_format`、`audio` | 当前音频工具只接受 mono S16_LE raw/16-bit WAV；转换后的工具输入与 SDK 原配置分别记录 |

`config.source` 写原始文件、行号及目标设备；`capabilities.source` 写匹配的对外文档版本、章节或公开头文件位置。该版明确支持的 TalkVQE 率可填 `[8000,16000]`，`layouts_without_aec` 可含 `AX_AI_MIC_MIC`；文档只建议 10 ms 帧长时，**不填**排他性的 `frame_samples=[80,160]`。`period_multiple_same_rate` 仅在确认同率设备周期就是该 VQE 输入长度时填写，跨重采样不套用。

`VqeEnabled/Bypass/DumpCount`、目标设备、采集点、完整处理配置、返回码及帧/播放事件没有对应的自动诊断字段，原始记录放 `text_evidence`，判断写入 diagnosis，不新增臆造的 schema 字段。`proc_audio.py` 当前仅提取 AI/AO 表格，不解析 AENC/ADEC；现有工具不自动做设备关联、状态联合判定、计数差分、错误码解码、活动 union 校验或 Get/Release 配对。`analyze.py` 的日志候选与额外处理冲突仍需 Agent 判读；后者会查看所有提取的 AI 行，必须核对设备/轮次。proc 没有产生 finding 不代表运行配置正确。

文件路径相对请求目录，禁止越界和指向目录外的符号链接。每个音频至多 32 MiB/120 秒，文本至多 2 MiB；超限选有时间标记的片段，多声道/非 16-bit 转换保留原格式和操作记录。类型错误或 NaN/Infinity 拒绝并退出 2；单文件错误记 input_errors，其余有效证据继续分析。既有输出不覆盖。

拆声道前确认采集点布局，真实 ref 取 VQE_REF/Rin；内部回环的无效声道和 AO 播放文件都不能顶替。Sin/Sou 间还有 NS/NSAdv、AGC、VAD 等处理或开关未确认时，不填 `aec_only_unity_gain=true`。时间前提独立核实，不能因为三份文件来自同一 SaveFile 调用就声明 sample 0 同步。

### 枚举、阶段与长度

以下依据对外 `ax_global_type.h/ax_comm_aio.h/ax_ai_api.h/ax_ao_api.h` 及上述 API 文档 §3。先确认日志输出的是枚举值、实际物理量还是格式化名称，再做转换：

| 现场字段 | 整理规则 |
|---|---|
| `AX_AUDIO_BIT_WIDTH_E` | 0/1/2/3 对应 8/16/24/32-bit；不能把 `enBitwidth=1` 解释为 1-bit |
| `AX_AUDIO_SOUND_MODE_E` | MONO=0、STEREO=1、QUAD=2；枚举值不等于声道数，转换时使用实际 1/2/4 声道 |
| 设备 `u32ChnCnt/u32PeriodSize` | AI 头文件注释列出 1/2/4/8 通道和 80/160/240/320/480/1024/2048/4096 周期点数；该版 API 文档对底层声卡注明当前仅支持 2chn，使用时核对匹配版本及板型能力。这些设备属性不能作为 VQE 的 `u32FrameSamples` 能力表 |
| `AX_AI_EnableResample` | 参数是 `enOutSampleRate`，结合该采集点的输入率与实际输出确认 |
| `AX_AO_EnableResample` | 参数是 `enInSampleRate`，不能把该值直接当设备播放率 |
| PCM frame / encoded stream 的 `u32Len` | 上述文档将 PCM frame 长度定义为 bytes，stream 头文件也明确为 bytes；不能直接填成 samples |

只有确认数据为无填充的 16-bit 交织 PCM、实际声道数为 C，且长度可整除时，才用 `u32Len / (2 × C)` 得到每声道样本数；编码流、24-bit 容器和其他布局另按各自格式处理。`AX_AUDIO_FRAME_T.u64VirAddr` 实际声明为 `AX_U8 *`，采集器应按指针类型处理，不能只按字段名假定为固定宽度整数；诊断通常只需帧元数据，不要求客户提交地址。

SDK 原始配置、各采集点格式与转换后的工具输入分开记录。设备周期点数、缓冲周期数、算法帧样本数和字节长度各用自己的单位，跨重采样不直接比较点数。

### delay 字段

在 request.json 中加入 `delay`，以下是该字段的示例值：

```json
{
  "enabled": true,
  "same_run": true,
  "shared_timebase": true,
  "capture_stage": "before_compensation",
  "max_lag_ms": 500,
  "window_ms": 1000
}
```

`same_run=true`、`shared_timebase=true` 和 `scenario=far_only` 必须有现场依据。`capture_stage` 可为 before_compensation / after_compensation / unknown。max_lag_ms 默认 500、范围 1–2000，搜索区间为 ±max_lag_ms；window_ms 默认 1000、范围 250–4000。单位均为 ms，这是工具范围，不是 SDK 参数范围。

可选 `delay.parameter` 含 name（公开参数名）、value_ms（实际值）、source（读回出处）、semantics、semantics_source（对外定义出处）、tolerance_ms（本次认可容差）。仅在 [delay.md](delay.md) 的总纯延迟条件成立时填 semantics=`total_ref_delay`；缓存分量、附加 offset、自动模式或含义未知时，仅记录已知 name/value_ms/source。负数实际值可记录，但不会自动比较。

## 三、诊断结果

脚本生成 measurements.json / measurements.md。Agent 按 [报告模板](response-template.md) 完成判断，写 diagnosis.json（schema_version=1），再用 render_report.py 生成 diagnosis.md，以下字段必备：

| 字段 | 约束 |
|---|---|
| status | 待补证据=needs_evidence / 待复测=pending_verification / 已解决=resolved |
| classification | 配置使用=configuration / 参考信号=signal_path / 时间连续性=timing / 处理效果=processing / SDK 嫌疑=sdk_suspected / 未定=inconclusive |
| summary | 结论与问题归属，区分事实和推断；归属不能从 classification 自动推定 |
| evidence | 对象列表，含 source（文件:行号、JSON pointer 或音频区间）、observation |
| hypotheses | 替代解释或待验证项的字符串列表 |
| actions | 非空对象列表，含 change、reason、rollback、expected、falsifier |
| missing_evidence | 缺什么、如何取得的字符串列表 |
| regression | 对象列表，scenario 至少含 far_only/near_only/double_talk/silence/trigger；每项含 criterion、status=pass/fail/not_run、evidence |
| resolution_evidence | 本次复测文件路径列表，可附 #定位；未复测为空 |

配置错误已证实时可用 pending_verification 并保留补采；仅有症状无定位依据用 needs_evidence/inconclusive。已解决必须满足客户判据、无未闭合缺项、分类不是 inconclusive/sdk_suspected、resolution_evidence 非空，且所有已列回归均有真实 pass 证据。未执行写 not_run 和原因。

## 四、交付检查

将允许使用的复测记录保存在输出目录，例如 verification/run-02.json，注明版本、前后配置、场景、判据、结果和原始材料位置。regression 的 pass/fail 及 resolution_evidence 引用相对输出目录的非空文件，可附 #定位，不得越界或引用四个生成报告自证。

```bash
python3 "<skill-dir>/scripts/render_report.py" --out "<new-out>"
```

该命令读取已完成的 diagnosis.json，保留所有证据、候选解释、动作、反证、回退、复测判据及补充字段，生成 diagnosis.md，并运行同一结构校验。它只排版，不补写诊断，不修改 JSON 或生成验收结论。输出 Markdown 已存在时拒绝覆盖；修正 JSON 后确认旧 Markdown 可替换，再删除该文件重跑。无需再手写同一份 Markdown，也无需重复调用校验器；通过后交付文件路径与简短结论。

已有手写 Markdown 时，可仅检查：

```bash
python3 "<skill-dir>/scripts/validate_report.py" --out "<new-out>"
```

校验通过返回 0，结构/状态/证据文件错误返回 2。四个结果文件须齐全；非 inconclusive 需有 evidence，needs_evidence 需有缺项。

校验器不验证录音真假、客户标准或 JSON/Markdown 语义一致性，交付前需核对实际内容。修正前 measurements 可保留原缺项，已解决报告须用本次后续证据说明如何补齐。
