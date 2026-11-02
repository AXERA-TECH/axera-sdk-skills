# 没有日志时如何抓取（Phase 2 前置，AX615 官方口径）

缺关键日志时**不要硬猜根因**。注意：**AX615 用的是自研 axsyslog 日志系统 + 内核 ramoops，不要套用通用 Linux 的 `dmesg` / `/var/log/syslog` / bootargs `loglevel`。** 下面按「运行期」和「挂死/崩溃」两类给官方抓法。命令/路径以实际 SDK 版本为准。

> 出处：《00 - AX SDK 使用说明》6.3/6.4（日志系统）、11.2（ramoops）；《25 - AX平台应用与内核Debug使用说明》；《57 - AX AOV解决方案说明》6.15.1；《11 - AX Watchdog 使用说明》。

## 一、运行期日志（axsyslog 体系）

- **SDK 各模块 log（ISP/IVPS/VENC/VDEC/SYS/NPU…）**：由 `axsyslogd` + `axklogd` 统一落盘到 **`/opt/data/AXSyslog/syslog/`**（默认 WARN 及以上）。用 `/bin/axdmesg` 查看 SDK 驱动输出的 kernel log（类似 dmesg）。
- **动态调日志等级**：`/proc/ax_proc/logctl`
  ```sh
  cat /proc/ax_proc/logctl                     # 看各模块当前状态/等级 + 用法说明
  echo klog 11 7 > /proc/ax_proc/logctl        # 把 SYS(id=11) 的 kernel log 提到 DEBUG(7)
  echo ulog 13 7 > /proc/ax_proc/logctl        # 把 IVPS(id=13) 的 user log 提到 DEBUG
  echo klog on   > /proc/ax_proc/logctl        # 开/关 kernel log(klog off 关闭)
  echo target console > /proc/ax_proc/logctl   # 把 user log 直接打到串口(user log only)
  ```
  常用模块 id：NPU=6、VENC=7、VDEC=8、SYS=11、IVPS=13、VIN=17（level 0–7，数字越小等级越高，默认 4=WARN）。**改 `logctl` 只当前开机有效**；要持久化改 `/etc/ax_syslog.conf` 后重启。
- **复现前 dump 一份 CMM 占用**（反查 owner 的基线，挂死后取不到）：
  ```sh
  ls /proc/ax_proc/
  cat /proc/ax_proc/mem_cmm_info > /tmp/cmm_before.txt   # 节点名以实际为准
  ```

## 二、挂死 / 崩溃场景（CPU 卡死、NMI 不响应、栈被截断）——本类问题刚需

硬挂时普通串口/文件日志往往抓不到栈（看门狗 WDT0 会因 deadlock 复位系统）。官方手段：

- **ramoops / pstore（首选，抓崩溃前的 console 与 oops/backtrace）**：内核已集成、默认关闭，需开 `CONFIG_PSTORE=y`（子开关：`PSTORE_CONSOLE` 存控制台输出、`PSTORE_RAM` 存 panic/oops、`PSTORE_FTRACE` 存函数调用序列）。崩溃后**热重启（复位，切勿断电——log 保存在 RAM）**，然后：
  ```sh
  ls  /sys/fs/pstore/
  cat /sys/fs/pstore/console-ramoops-0     # 崩溃前的控制台输出
  cat /sys/fs/pstore/dmesg-ramoops-0       # 崩溃时的 oops / backtrace
  ```
- **串口还在、但无法输入命令时**（外设回调/挂死场景，《AOV 方案》6.15.1）：
  ```sh
  echo 7 > /proc/sys/kernel/printk                          # 抬高 printk 等级
  echo 0 > /sys/module/printk/parameters/console_suspend    # 禁止 console 在 suspend 时挂起
  ```
- **背景**：WDT0 是 CPU 专用看门狗，用于防 deadlock、超时复位系统——所以这类挂死会自动重启，正好配合 ramoops 在重启后读出崩溃日志。

## 三、稳定复现

- 找到最小复现路径（哪条流、哪个退出动作触发），记录**多线程/多模块的退出顺序**——本类问题极依赖时序。
- 提高频率：反复 start/stop、切分辨率、压测退出路径；记录概率（如「10 次挂 3 次」），供判断改动是否有效。

## 四、需要向用户要齐的清单

1. 串口完整 log + `/opt/data/AXSyslog/syslog/` 下的日志（含挂死前若干秒）。
2. 若已复位过：`/sys/fs/pstore/console-ramoops-0`、`dmesg-ramoops-0`（完整崩溃栈）。
3. 复现前的 `/proc/ax_proc/mem_cmm_info` 快照。
4. 芯片型号 + SDK/BSP 版本。
5. 出问题数据流经过的模块 + 完整调用序列（含所有 `MemAlloc/MemFree/Mmap/Munmap/Get*/Release*`）。
6. 复现步骤与概率。

## 五、拿到日志后

回到 Phase 2：跑 `scripts/scan_cmm_log.sh`，对照 `log-keywords.md` 判读，抽出 `phyaddr`，再进 Phase 3。

> 若最终日志里始终没有任何 CMM/pool 关键字，且现象也不符合识别特征，应如实告知「当前证据不支持 CMM 错误释放这一路径」，不要为了套结论而过度解读。
