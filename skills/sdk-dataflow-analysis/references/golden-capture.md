# 数据流问题 Golden 采集基线

用于 AX615/MC20L 模块数据流问题的新增 Case。采集目标是保留同一复现轮次的应用时序、板端系统日志和数据面状态，方便分析 Skill 区分根因、传播错误和无关噪声。

## 采集前

先读取 `/proc/ax_proc/logctl`，以表中模块 ID 为准。将 VIN、IVPS、VENC 的 userlog 调到 info；当前 AX615 固件的 info 值为 `6`：

```sh
echo ulog 17 6 > /proc/ax_proc/logctl
echo ulog 13 6 > /proc/ax_proc/logctl
echo ulog 7 6 > /proc/ax_proc/logctl
cat /proc/ax_proc/logctl
```

保存调级后的完整 `logctl` 快照。只有 VIN、IVPS、VENC 的 `level(U)` 都为 `6` 才满足采集门槛。模块 ID 或等级定义变化时，以目标固件的 `logctl` 用法和模块表为准。

## 采集窗口

1. 清理上一轮应用进程，记录复现命令、SDK/APP 版本、板卡和 AXP hash。
2. 从应用启动前开始抓串口，至少持续到首次错误及其后续传播现象出现。
3. 保存 `logserviced` 实际写入的 syslog 文件或覆盖复现窗口的原始切片。该固件的常见目录为 `/tmp/data/AXSyslog/syslog/`；`logread` 不一定可用。
4. 异常稳定出现后立即抓 proc，记录每个文件对应的节点。proc 必须与该轮应用进程同属一个现场。

## 数据流 proc 基线

先 `ls` 确认节点存在，再读取。AXDF-001 使用以下节点：

```text
VIN:
  /proc/ax_proc/vin/attr
  /proc/ax_proc/vin/statistics
  /proc/ax_proc/vin/mode
  /proc/ax_proc/vin/ife_itp_hsk

IVPS:
  /proc/ax_proc/ivps
  /proc/ax_proc/ivps_sched

VENC:
  /proc/ax_proc/venc

Link/SYS:
  /proc/ax_proc/link_table
  /proc/ax_proc/link_table_kernel
  /proc/ax_proc/sys/vin_ivps_mode
  /proc/ax_proc/syncagent
```

建议分别保存为 `vin.proc`、`ivps.proc`、`venc.proc`、`link.proc`。若节点不存在，在 `case.yaml` 中写明，不创建看似成功的空文件。

## Case 输入与隔离

建议输入至少包含：

```text
input/serial.log
input/syslog.log
input/logctl.proc
input/vin.proc
input/ivps.proc
input/venc.proc
input/link.proc
```

每个 Case 目录固定两个区：`input/` 放分析阶段可读的现场材料，`answer/` 放 `case.yaml`、`oracle.yaml`、`reproducer.patch`，只在评分阶段读取；本文后续提到的 `case.yaml` 均指 `answer/case.yaml`。`case.yaml` 记录 syslog 原始路径、是否截取、字节或时间范围，以及串口和 proc 是否来自同一轮等采集元数据。由于 `case.yaml` 位于 `answer/`，这些元数据在盲测阶段对分析器不可见，因此凡是定位必需的线索（例如 syslog 实际覆盖的时间区间）必须能从 `input/` 文件自身读出，不能只写在 `case.yaml` 里。

## 完整性门禁

- 输入清单中的文件存在且非空。
- `logctl.proc` 可证明 VIN、IVPS、VENC userlog 为 info。
- 串口包含启动命令或版本、首次失败点和至少一个传播现象。
- `link.proc` 能显示异常 Link 是否进入 link table；失败 Link 缺失本身是有效证据。
- syslog 的来源与截取范围可追溯。syslog 中的晚发错误按时间排序分析，不能覆盖更早的 Link 失败。

## syslog 轮转陷阱

数据流停住后，部分模块会以极高频率输出错误 token（实测停流后 `[Cx][ENC][E]` 的 AXLOG2 token 可在十几秒内写满 1 MB 以上），`logserviced` 的切片随之快速轮转，**故障时刻的 syslog 往往在采集时已被冲掉**。

因此：

1. 复现前先清空或记录 `/tmp/data/AXSyslog/syslog/` 的文件列表，使采集窗口可追溯。
2. 异常出现后尽快抓取，不要等观察结束再采。
3. 若 syslog 仍未覆盖故障时刻，在 `case.yaml` 的 `capture.notes` 写明实际覆盖区间及原因，并指明首个现象应从 `serial.log` 读取；不要因此丢弃 syslog，停流后的连锁错误仍是有效的传播证据。
