# sdk-bsp-build 测试用例

本包提供 5 个独立的离线方案评测用例，检查技能是否给出正确目录、命令及前提。离线方案评测不执行真实固件编译，也不共享 Case 之间的运行状态；本交付包不提供原内部自动评测工作流。Case 2、5 的前提由评测任务明确给定，不能据此宣称真实构建已通过。

以下是实际 SDK 上的测试步骤。`AX615_ROOT` 替换为实际 SDK 根目录；`PROJECT` 必须选自 Case 1 的实际输出。Shell 中使用 `"$PROJECT"`，不要把 Makefile 变量写法 `$(PROJECT)` 当作 Shell 命令替换。

执行前确认 `clean` 将清理所选工程或模块的构建产物。

## Case 1：发现工程

目的：通过当前 SDK 的 `plist` 确认有效工程，仅发现工程，不考虑条件模块。

```bash
cd "$AX615_ROOT/build"
make plist
```

检查：命令退出码为 0，保存实际工程列表。不在 `build/out` 或 images 目录执行；不编造工程及模块归属。

## Case 2：完整编译并生成 AXP

前提：Case 1 成功，选择实际列出的工程，例如输出包含 `AX615_fastnor` 时：

```bash
PROJECT=AX615_fastnor
cd "$AX615_ROOT/build"
make p="$PROJECT" clean all install axp -j64
```

目的：完整编译、安装组件并生成 AXP，建立后续快速生成的前置产物。

检查：执行前记录开始时间，退出码为 0、没有导致构建失败的错误，确认 `build/out` 下所选工程的 AXP 为本次创建或更新。保存 SDK 路径、工程、命令、退出码和产物信息，供 Case 5 核对。

## Case 3：单编 BL1

前提：`PROJECT` 是 Case 1 确认的有效工程。

```bash
cd "$AX615_ROOT/boot/bl1"
make p="$PROJECT" clean all install -j64
```

目的：只编译并安装 BL1。检查退出码与编译安装日志，不追加其他模块或 AXP 打包命令。

## Case 4：单编 Linux

前提：`PROJECT` 是 Case 1 确认的有效工程。

```bash
cd "$AX615_ROOT/kernel/linux"
make p="$PROJECT" clean all install -j64
```

目的：只编译并安装 Linux。检查退出码与编译安装日志，不依赖任何假定存在的 rootfs 文件，不追加其他模块或 AXP 打包命令。

## Case 5：快速生成 AXP

前提：Case 2 已在同一 SDK、同一 `PROJECT` 下成功，相关组件产物已构建安装。若前提不满足，先完成 Case 2。

```bash
cd "$AX615_ROOT/build/projects/$PROJECT"
make p="$PROJECT" clean all install axp
```

目的：使用已安装组件重建项目 image 并生成 AXP。命令不带任何 `-j`。

检查：执行前记录开始时间，确认退出码为 0、无终止错误，并验证所选工程的 AXP 为本次创建或更新；历史包不能视为本次成功结果。

## OP-TEE 配置说明

OP-TEE 不属于上述单编用例。它依赖所选工程的有效 `SUPPORT_OPTEE` 配置；只有 `SUPPORT_OPTEE=TRUE` 时才编译，不能假定所有工程都会编译 OP-TEE。
