# AX615 Linux SD 卡诊断输出模板

先写当前 Linux 代码基线和故障层级；缺失项写“未提供，不能判断”，不要补猜。日志、路径、命令和代码标识符保持原样。

```text
结论等级：已确认 / 高可信待验证 / 信息不足
代码基线：kernel/linux/linux-4.19.125
故障阶段/层级：driver/module / Linux probe / card detect / power-pin / card enumeration / voltage-timing / block I/O / partition-filesystem / userspace-hotplug / 未知
环境：AX615 型号/revision、板型、SD 卡型号/容量/速度、kernel/DTB/rootfs/模块版本
最后成功阶段：<由日志确认的最后一步>
首个异常：<保留原始日志和时间顺序>
结论：<一句话，严格不超过当前证据范围>
依据：
- 日志：<原文片段及前后顺序>
- 代码：<当前工作区文件、函数或日志路径>
- 配置/DTB：<实际 .config、built-in/module、.ko、目标 DTB 和 GPIO/card detect 证据；未提供则写明>
- 对照：<成功卡、低速模式、polling/detect、正常 umount 或复现 A/B；未提供则写明>
机制：<仅解释被依据支持的因果关系>
客户可验证：
1. <低风险命令或动作>
   预期：<观察结果>
   含义：<结果如何改变判断>
2. <一次只改变一个变量的对照>
   预期：<观察结果>
   含义：<结果如何改变判断>
反证条件：<出现什么结果就不能继续维持当前判断>
边界：<当前证据不能推出的结论>
下一步：<按优先级列出仍需补充的日志、版本、DTB、模块、卡信息或硬件取证>
```

## 使用规则

- `已确认` 只用于日志/代码/配置或 A/B 已闭合的结论；例如 `mount` 显示 `(ro)` 时，可以确认当前挂载是只读，但不能顺便确认卡损坏。
- `高可信待验证` 用于代码路径和现场现象高度匹配、但仍缺目标 DTB、实际 config/模块、对照或硬件证据的方向。
- `信息不足` 用于只有“识别不到”“挂载失败”“偶发错误”等描述，或缺少首个异常和阶段信息的情况。
- 至少写一个反证条件；例如驱动已确认 built-in 且 probe 完成，但更换 `cd-gpios` 极性仍无 CMD 响应，不能继续只把问题归因于 module 未加载。
- `mount failed`、readonly、`card removed` 和 I/O error 必须结合时间顺序；不能把最后一行当作根因。

## 卡识别不上时的固定输出顺序

当用户只说“SD 卡识别不上”或没有 `/dev/mmcblk*` 时，按以下顺序给出检查，不要直接建议换卡：

1. 实际 `.config`/`/proc/config.gz`：`CONFIG_MMC*`、`CONFIG_MMC_SDHCI*`、`CONFIG_MMC_SDHCI_AXERA` 是 `=y`、`=m` 还是未启用；
2. 若 `=y`：说明无需 `insmod`，检查 `dmesg` 中 probe；若 `=m`：查 `.ko`、依赖、`lsmod`，必要时 `modprobe`/`insmod` 并保存错误；
3. 目标 DTB：`compatible`、`status`、`reg`、`interrupts`、GPIO 和 host 能力；
4. card detect：`broken-cd` polling 或 `cd-gpios` detect，进一步检查 `cd-inverted`、debounce、pinmux、电平和中断；
5. 供电：`pwr_en_gpioD/Q`、`pwr_sw_gpio`、无电源 GPIO 时的保持供电路径、上电延时和电压稳定日志；
6. 管脚上下拉：确认原理图/实测和当前 pinmux，不能假设驱动动态完成上下拉；
7. 最后才分析 MMC enumeration、CRC/timeout 和卡兼容性。

## 文件系统损坏、readonly 与安全拔卡

- FAT32/VFAT/exFAT 出现损坏、readonly 或 mount 失败时，必须询问卡是否曾经在挂载状态下直接拔出或异常断电。
- 明确告知：写入后应先 `sync`，再 `umount`，确认 `mount` 中已不再挂载后才能拔卡；`umount: device is busy` 时先查 `fuser`/`lsof`，不能忽略 busy。
- 未 `umount` 直接拔卡可以解释后续的元数据损坏、mount 失败、自动 readonly 或 I/O error，但不能据此断言 SDHCI/卡硬件损坏。
- 若 `I/O error` 发生在 `card removed` 之后，优先作为热拔卡后果分析；若发生在卡正常插入且未发生拔卡期间，再结合 PHY/tuning/供电/CRC 证据。

## 常见日志的最小响应范围

| 日志或现象 | 可以直接确认 | 仍需补充/不能直接推出 |
|---|---|---|
| 只有“没有 `/dev/mmcblk*`” | Linux userspace 未看到 block 设备 | 需先区分 `=y`/`=m`、`.ko`/依赖、DTB、card detect、供电和枚举 |
| `modprobe: module ... not found` | 当前 module 查找路径没有找到目标模块 | 可能是未打包、版本不匹配或驱动是 built-in；不能直接确认源码缺驱动 |
| 已知 `CONFIG_MMC_SDHCI_AXERA=y` 但没有 probe 日志 | built-in 驱动理论上应随内核启动匹配 | 需核对实际 kernel、DTB `status/compatible`、日志级别和启动镜像 |
| `axera sdhci probe` 后无后续 check | AXERA probe 未完成或日志不完整 | 需完整 probe、返回值、DTB、模块和实际镜像 |
| `broken-cd` | 使用软件 polling card detect | 插卡后检测有延迟；不能直接判 polling 失效 |
| `cd-gpios` + `cd-inverted` | 使用 GPIO detect 且信号极性反转 | 需实测 GPIO 电平、pinmux、debounce 和中断；不能只看字段名 |
| `phy lock failed` | PHY DLL lock 路径失败 | 不能单独断言 PHY delay 错误、供电坏或 PCB 问题 |
| `no tuning point found` | tuning 没找到有效采样窗口 | 需模式、频率、电压、卡和低速对照；不能直接判卡坏 |
| `AX615D SD mst only design 3.3V, not support UHS` | 当前代码按 AX615D 能力限制 UHS | 不能把没有 UHS/1.8 V 当成 SD 卡故障 |
| `mount` 显示 `(ro)` | 当前挂载是只读 | 需区分显式 `-o ro`、写保护、I/O 错误、文件系统损坏和驱动降级 |
| `FAT-fs`/`exFAT` 显示 `not properly unmounted` 或 `read-only` | 文件系统检测到未正常卸载或进入只读路径 | 需核对是否直接拔卡/异常断电、首次 I/O 错误和设备只读状态 |
| `umount: device is busy` | 仍有进程占用挂载点 | 需用 `fuser`/`lsof` 找占用，不能此时拔卡 |
| `card removed` 后 I/O error | 热拔卡或检测到移除后传输失败的候选 | 需按时间顺序确认是否是预期拔卡事件 |
| 只有“mount failed” | mount 操作失败 | 需提供 block device、分区、文件系统类型、模块、umount/拔卡历史和完整 `dmesg` |

## 反证示例

- 如果驱动已确认 `=y` 且 probe 完成，`insmod` 不是下一步；应转向目标 DTB、card detect、供电和 pinmux。
- 如果 `broken-cd` polling 与 `cd-gpios` detect 的目标配置被确认，但二者都在正常电平下枚举失败，不能继续只归因于 card detect。
- 如果正常执行 `sync` + `umount` 后仍稳定出现同一文件系统损坏，不能继续把问题只归因于直接拔卡；需检查 I/O、供电和文件系统工具。
- 如果低速模式和高速模式都出现相同 CRC/timeout，不能继续只把问题归因于 tuning 或高速信号。
- 如果 `/dev/mmcblk*`、分区和文件系统均可读，只有某个应用打开路径失败，不能把应用错误回溯成 SDHCI probe 失败。
