# 输入完整性与板端补采

以 AXDF-001 为基线。每次分析必须有同一复现轮次的 `serial.log`、`syslog.log`、`logctl.proc`、`vin.proc`、`ivps.proc`、`venc.proc`、`link.proc`，并先通过 `scripts/check_input.py`。

## 补采原则

- 抓取前执行 `mkdir -p /tmp/ax-dataflow-input`。
- 先把 VIN、IVPS、VENC userlog 调到 info，再保存 `logctl.proc`。当前 AX615 固件对应模块 ID 为 17、13、7，info 值为 6；若固件表发生变化，以 `/proc/ax_proc/logctl` 为准。
- 串口从应用启动前开始录制。异常稳定出现后、应用仍在运行时抓 proc。
- `syslog.log` 必须覆盖本轮复现窗口。优先从 `logserviced` 当前打开的文件获取，不假设板端存在 `logread`。
- 如果只缺 proc 且原现场仍在，可以补抓对应 proc；如果现场已结束，或缺串口/syslog，重新复现并采集七项完整输入。
- 板端节点不存在或读取失败属于采集失败。保留错误并报告，不创建空文件。

## 板端命令

先设置并验证 userlog：

```sh
mkdir -p /tmp/ax-dataflow-input
echo ulog 17 6 > /proc/ax_proc/logctl
echo ulog 13 6 > /proc/ax_proc/logctl
echo ulog 7 6 > /proc/ax_proc/logctl
cat /proc/ax_proc/logctl > /tmp/ax-dataflow-input/logctl.proc
```

通过当前板卡会话从应用启动前开启串口录制，运行 Case 的复现命令，持续到首次异常及其传播现象出现；控制端保存完整会话为 `serial.log`。串口采集不能只用应用 stdout 代替，因为 SYS/kernel 信息可能直接写 UART。

应用仍在运行时抓 proc：

```sh
{
  for node in attr statistics mode ife_itp_hsk; do
    echo "===== /proc/ax_proc/vin/$node ====="
    cat "/proc/ax_proc/vin/$node"
  done
} > /tmp/ax-dataflow-input/vin.proc

{
  for node in /proc/ax_proc/ivps /proc/ax_proc/ivps_sched; do
    echo "===== $node ====="
    cat "$node"
  done
} > /tmp/ax-dataflow-input/ivps.proc

cat /proc/ax_proc/venc > /tmp/ax-dataflow-input/venc.proc

{
  for node in /proc/ax_proc/link_table /proc/ax_proc/link_table_kernel \
              /proc/ax_proc/sys/vin_ivps_mode /proc/ax_proc/syncagent; do
    echo "===== $node ====="
    cat "$node"
  done
} > /tmp/ax-dataflow-input/link.proc
```

定位 `logserviced` 当前输出并保存 syslog：

```sh
LOGSERVICE_PID=$(pidof logserviced | awk '{print $1}')
SYSLOG_PATH=
for fd in /proc/$LOGSERVICE_PID/fd/*; do
  path=$(readlink "$fd")
  case "$path" in /tmp/data/AXSyslog/syslog/*.log) SYSLOG_PATH=$path; break;; esac
done
[ -n "$SYSLOG_PATH" ] || { echo "未找到 logserviced 当前 syslog" >&2; exit 1; }
cp "$SYSLOG_PATH" /tmp/ax-dataflow-input/syslog.log
```

将 `/tmp/ax-dataflow-input/` 下的六个板端文件和控制端 `serial.log` 传入 Case 的 `input/`。运行：

```sh
python3 <skill-dir>/scripts/check_input.py <input-dir>
```

其中 `<skill-dir>` 是 `sdk-dataflow-analysis/SKILL.md` 所在目录。只有返回 `PASS` 才开始根因分析。
