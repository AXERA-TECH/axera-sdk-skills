# ffprobe 码流分析

## 提取字段

`analyze_bitstream.py` 从 `-show_streams/-show_format` 读取 codec、profile、level、尺寸、帧率和时长，从 `-show_frames` 读取 `key_frame`、`pict_type`、时间戳和帧大小，从 `-show_packets` 读取 packet size 与时间戳。

## 指标定义

- GOP 长度：相邻 `key_frame=1` 的帧序号距离；同时报告最小、最大和中位数。
- I/P 大小比：平均 I 帧大小除以平均 P 帧大小；缺少任一类型时报告未知。
- I 码量占比：I 帧 packet/frame 大小之和除以视频帧大小总和。
- 码率：按时间戳覆盖区间计算总字节×8/秒，并报告平均值；按 1 秒窗口报告峰值。
- 帧率：优先使用时间戳差分，并与 stream 声明值比较。

## 限制

ffprobe 通常不显示硬件 RC 的实际 QP、CTU QP map、ROI 或内部场景复杂度。码流统计可支持“结构异常/码量异常”的结论，但不能独立证明主观呼吸效应或某个 QP 字段是唯一根因。
