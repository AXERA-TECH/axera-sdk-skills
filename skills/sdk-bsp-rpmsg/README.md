# sdk-bsp-rpmsg

Axera M57/AX637 IPC、RPMsg 和 RPZC skill 包，覆盖 M57 Linux/QNX 主域、AX637/AX637R 非 QNX 场景与 SafetyIsland MCU/RTOS/MCAL 对端的配置、使用、联调和故障定位。

## 适用场景

- 配置 Linux 或 QNX 主域的 RPMsg 物理通道、endpoint、mailbox/GPIO 通知和 shared memory（QNX 仅适用于 M57，AX637 不支持 QNX）
- 配置及使用 RPZC（IPC Zero Copy）buffer，处理创建、传输、接收、ACK 和销毁
- 联调主域与 SafetyIsland MCAL/RTOS 的 endpoint、buffer、地址、方向和 reset/reinit
- 根据设备树、内核配置、驱动日志和 MCAL/RTOS 状态定位通信失败

## 目录结构

```
sdk-bsp-rpmsg/
├── SKILL.md              # 触发条件、路由、操作流程与安全边界
├── skill-card.md         # 元数据、平台矩阵、风险与来源
├── routing.yaml          # M57/AX637 平台识别与加载规则（AX637 不支持 QNX）
├── platforms/
│   ├── m57.md            # M57 公共 IPC/RPMsg/RPZC 事实
│   └── ax637.md          # AX637/AX637R 的复用与确认事项
├── reference/
│   ├── ax_ipc.md          # Linux/MCAL/RTOS IPC/RPMsg/RPZC 知识库
│   ├── ax_ipc_FAQ.md      # M57 问题复盘与平台适用范围
│   ├── assets/ax_ipc_FAQ/ # FAQ 本地图片
│   ├── _index.md           # 实际参考文档与本地 FAQ 路由表
│   ├── *补充*.md         # AI 补充说明
│   └── *.docx            # 原始 Linux、QNX、MCU 用户指南
├── scripts/install.py   # 运行包投影，排除评测答案
├── tests/
│   ├── test_ci.py        # 资料、安装包与断言的静态测试
│   └── manual/           # 五项人工验收材料，不进入自动用例发现
└── evals/
    ├── suite.yaml        # 评测用例清单（需另行配置评测执行器）
    ├── cases/            # 四个已在 suite 登记的核心门禁
    ├── m57/tasks.yaml    # 原始验收任务记录，非可执行 suite
    └── ax637/tasks.yaml  # 原始验收任务记录，非可执行 suite
```

## 平台与参考资料

| 平台/域 | 事实入口 | 主要参考内容 |
|---|---|---|
| Linux 主域 | [`platforms/m57.md`](platforms/m57.md) | [`reference/ax_ipc.md`](reference/ax_ipc.md)、Linux 指南及其补充 |
| QNX 主域（仅 M57） | [`platforms/m57.md`](platforms/m57.md) | QNX `ax_ipc` 驱动、EPT/IPCZC 配置、IRAM/DDR、通知方式及测试入口；AX637 不支持 QNX |
| MCU 域 MCAL | [`platforms/m57.md`](platforms/m57.md) | [`reference/ax_ipc.md`](reference/ax_ipc.md)、MCU IPC/IPCZC 指南及其补充 |
| MCU 域 RTOS | [`platforms/ax637.md`](platforms/ax637.md) | [`reference/ax_ipc.md`](reference/ax_ipc.md)、RT-Thread IPC 驱动与测试入口 |
| FAQ | [reference/ax_ipc_FAQ.md](reference/ax_ipc_FAQ.md) | 本地问题复盘与图片，保留来源标题和版本，可离线读取 |

读取参考资料时必须先看 [`reference/_index.md`](reference/_index.md)，再按场景读取 [`reference/ax_ipc.md`](reference/ax_ipc.md) 与对应指南；FAQ 问题读取 [reference/ax_ipc_FAQ.md](reference/ax_ipc_FAQ.md)，无需访问内网；维护来源的在线入口与运行时交付文档分离，更新后同步本地正文和必要图片。原始 docx 只在发现错误时修改，新增说明写入对应补充 md。本轮同步 Linux、MCAL、RTOS 和 QNX 的 skill 文档；QNX 专属事实仅适用于 M57，AX637 不支持 QNX，QNX 相关修改无需同步到 AX637。

## 使用流程

1. 确认主域（Linux/QNX；QNX 仅适用于 M57，AX637 不支持 QNX）、SafetyIsland 对端（R0/R1、RTOS/MCAL）、芯片/板型和 SDK 版本。
2. 确认两端的物理通道、endpoint 地址/name、RPZC buffer name/size/方向、shared memory 地址及通知方式。
3. Linux 核对 defconfig、DTS、`/sys/class/rpmsg` 和 `/dev/rpmsg_ctrlX`；M57 的 QNX 核对 `kernel/osdrv/open_drv/ax_ipc/` 下的 `driver/cfg`、`driver/rpmsg`、`driver/rpzc`、`lib`、EPT/IPCZC 配置和实际 resource manager；MCAL 核对 `Ipc_cfg`/`Ipc_zc_cfg`，RTOS 核对 `SafetyIsland/rt-thread/bsp/m57/drivers/ipc/` 下的 `cfg/`、`rpmsg/` 和 `rpzc/`。AX637 不执行 QNX 核对流程。
4. 对 M57 QNX，默认 IPCZC 使用 IRAM，通知默认采用 `IPC_GPIO_TRIGGER_IRQ_EN=1` 对应的 GPIO + SPI slave CS/回主域 mailbox 方案；切换 DDR 或 mailbox 时，必须同步修改 QNX reserved-memory、`Ipc_zc_cfg.h`、`Ipc_cfg.h` 和 MCU 端配置。可用 `pidin syspage=asinfo` 核对 QNX reserved-memory；AX637 不支持此流程。
5. 先完成 RPMsg 链路和 name service，再创建/检查 RPZC buffer；不要把 mailbox/GPIO 当业务 payload 通道。
6. 按双向消息、buffer 可用性、ACK、超时、destroy 和远端 reset 场景验证，并记录两端日志和 errno/返回值。M57 QNX 基础测试使用 `sample_ipc_rpmsg`，RPZC 测试使用 `sample_ipc_rpmsg -z 1 [-t n]`；AX637 使用其实际 Linux/RTOS 测试入口。

## 评测材料

`evals/cases/` 保留 `routing-conflict`、`m57-rpmsg`、`ax637-boundary` 和 `m57-rpzc` 四个核心场景。按用例 `case.yaml` 向分析器提供输入及运行资源，由评测方独立执行 `assert.sh`，答案不交给分析器。结构化断言不能代替完整自然语言语义审核。

`tests/manual/` 保留分平台人工验收材料。旧文本断言仅供辅助，不能代替人工判断。本交付包不提供原内部自动评测工作流；评测材料不证明模型、SDK 构建或实板验证已经通过。

本地独立测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

样例、设备节点、shared-memory 地址及 ACK/reset 行为须依据目标 SDK、两端镜像和板端日志核实。

## 关键边界

- DTS、MCAL/RTOS 配置和实际内存布局必须成对修改；不能只改一端的 slot、地址、name 或 service。
- RPZC 收到需要 ACK 的描述符后，必须先消费 payload，再回复 ACK；同步发送端在 ACK 前不能复用 buffer。
- 远端 remove/reset 后，原有 RPMsg/RPZC fd 和 mmap 不保证继续有效，必须重新枚举和初始化。
