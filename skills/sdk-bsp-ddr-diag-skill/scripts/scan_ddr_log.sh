#!/bin/sh
# scan_ddr_log.sh — 扫描 AX615 SDK/BSP 串口启动日志中的 DDR 初始化、Training 与 BIST 关键字。
# 与 sdk-bsp-ddr-diag-skill 的 reference/FAQ.md 和 code_map.md 保持一致。
# 用法: sh scan_ddr_log.sh <logfile>
# 兼容 busybox sh / Mac / Linux PC。

LOG="${1:-}"
if [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
    echo "用法: sh $0 <logfile>"
    exit 2
fi

echo "==== 扫描 AX615 DDR 日志: $LOG ===="

# $1=说明  $2=grep 扩展正则；打印命中数，命中则附前 5 行样例
scan() {
    n=$(grep -Ec "$2" "$LOG" 2>/dev/null)
    [ -z "$n" ] && n=0
    echo "[$n] $1"
    if [ "$n" -gt 0 ]; then
        grep -En "$2" "$LOG" | head -n 5 | sed 's/^/        /'
    fi
}

echo "---- 关键字命中 (按阶段) ----"
scan "初始化握手/轮询超时 (DFI/PHY pre-init)"  'dfi polling[ ]*timeout|polling .* timeout'
scan "读/写 Training 失败 (Read/Write Eye)"    'read eye training fail|write deskew training fail|write eye training fail'
scan "BIST/Memtest 失败 (地址/模式错误)"       'bist fail|BIST_.*fail'

echo "---- 提取配置锚点 (用于 S1 确认环境与分支) ----"
echo "芯片与 DDR 类型 (chip_type / ddr_type):"
grep -iE 'chip_type|ddr_type|dram type' "$LOG" | sort -u | sed 's/^/        /'
echo "频率/时钟配置 (Freq/MHz/Mbps):"
grep -iE 'ddr.*freq|clk.*ddr|MHz|Mbps' "$LOG" | sort -u | sed 's/^/        /'
echo "BIST 测试范围与 Pattern 锚点:"
grep -iE 'BIST_ALLWRC|BIST_ONEWRC|bist init|bist test' "$LOG" | head -n 5 | sed 's/^/        /'

echo "---- 初判与 S2/S3 排查指引 ----"
if grep -Eqi 'dfi polling[ ]*timeout' "$LOG"; then
    echo "  [!] 检测到 DFI 轮询超时。下一步:"
    echo "      1) 参考 reference/FAQ.md 中的 FAQ-DDR-005;"
    echo "      2) 此报错发生在 Training 之前，优先排查时钟、PHY pinmux 和 VDDQ 供电。"
elif grep -Eqi 'read eye training fail|write deskew training fail|write eye training fail' "$LOG"; then
    echo "  [!] 检测到 Training 阶段失败。下一步:"
    echo "      1) 参考 reference/FAQ.md 中的 FAQ-006 / FAQ-007;"
    echo "      2) 确认是读写双挂，还是仅写路径挂；优先核对共同前置条件 (位宽/Rank/协议)。"
elif grep -Eqi 'bist fail' "$LOG"; then
    echo "  [!] 检测到 BIST 测试失败 (Training 可能已通过)。下一步:"
    echo "      1) 参考 reference/FAQ.md 中的 FAQ-008 / FAQ-009;"
    echo "      2) 提取 BIST 锚点，整理 BIST 结果矩阵，确认是否覆盖了有效内存。"
else
    echo "  [ ] 未发现明确的 DDR 初始化/训练失败关键字。"
    echo "      若机器仍启动失败，请进入 SKILL.md 的 S0 阶段，确认当前日志是否抓全了 SPL 早期信息。"
fi