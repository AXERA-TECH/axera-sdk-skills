#!/bin/sh
# scan_cmm_log.sh — 扫描 AX SDK/BSP 日志中的 CMM/pool/NOMEM 错误关键字，抽取 phyaddr/BlockId 锚点并给初判。
# 与 references/log-keywords.md 及 references/nomem-diagnosis.md 的关键字保持一致。
# 用法: sh scan_cmm_log.sh <logfile>
# 兼容 busybox sh / 目标板与 PC。

LOG="${1:-}"
if [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
    echo "用法: sh $0 <logfile>"
    exit 2
fi

echo "==== 扫描日志: $LOG ===="

# $1=说明  $2=grep 扩展正则；打印命中数，命中则附前 5 行样例
scan() {
    n=$(grep -Ec "$2" "$LOG" 2>/dev/null)
    [ -z "$n" ] && n=0
    echo "[$n] $1"
    if [ "$n" -gt 0 ]; then
        grep -En "$2" "$LOG" | head -n 5 | sed 's/^/       /'
    fi
}

echo "---- 关键字命中 ----"
scan "ax_cmm_free / Block not found  (非法·重复·跨所有权释放)" 'ax_cmm_free failed|Block not found'
scan "Pool BlockId invalid           (失效句柄仍被使用)"       'BlockId :0x[0-9a-fA-F]+ invalid|handle2poolid|handle2physaddr'
scan "giveback_to_pool virt get fail (归还时 block 已失效)"    'giveback_to_pool|frame node virt get fail'
scan "blocks are not free            (退出未释放·泄漏)"        'blocks are not free|should not be unregistered'
scan "CMM 分区内存不足 (物理空间超限/NOMEM)" 'CMM partition memory isn'\''t enough|mem agent malloc failed|ax_block_alloc.*failed'
scan "底层 Pool 创建失败 (连续内存不足/NOMEM)" 'create pool failed|Creat user pool fail|Init.*MbufPool fail'
scan "NOMEM/NOBUF 经典错误码 (0x...18/0x...80)" '0x80070218|0x80110118|0x80110180'
scan "码流环形缓冲满 (BufFull / 0x80070221)" 'BufFull|bBuffFull|0x80070221'
scan "退出流程标志                    (定位出问题的阶段/模块)"  'ivps_sched_chn_disable|session_deinit|StopRecvPic|_Deinit|Destroy'

echo "---- 锚点地址 (交给 Phase 3 反查 owner) ----"
echo "phyaddr:"
grep -oE 'phyaddr=0x[0-9a-fA-F]+' "$LOG" | sort -u | sed 's/^/       /'
echo "BlockId:"
grep -oE 'BlockId :0x[0-9a-fA-F]+' "$LOG" | sort -u | sed 's/^/       /'

echo "---- 初判 ----"
if grep -Eq 'CMM partition memory isn'\''t enough|mem agent malloc failed|create pool failed|Creat user pool fail|0x80070218|0x80110118|0x80110180' "$LOG"; then
    echo "  [!] 检测到系统/CMM 物理内存不足 (NOMEM)。下一步:"
    echo "      1) 对照 references/nomem-diagnosis.md 查看具体是哪个 Partition/Pool 耗尽;"
    echo "      2) 确认申请的 size 与分区 Free 容量差距;"
    echo "      3) 评估是静态分区划分偏小，还是业务过度申请/分辨率未合理规划。"
elif grep -Eq 'BufFull|bBuffFull|0x80070221' "$LOG"; then
    echo "  [!] 检测到 VENC 码流环形缓冲满 (BufFull / 0x80070221)。"
    echo "      参考 references/nomem-diagnosis.md 检查码流 buffer 大小或应用取流时效。"
elif grep -Eq 'ax_cmm_free failed|Block not found' "$LOG"; then
    echo "  [!] 检测到 CMM 非法/重复释放。下一步:"
    echo "      1) 取上面的 phyaddr 作锚点;"
    echo "      2) 按 references/proc-and-apis.md 反查该 phyaddr 的 owner(token);"
    echo "      3) 按 references/cmm-ownership-rules.md 审调用配对(重点:取帧后是否又 MemFree)。"
elif grep -Eq 'BlockId :0x[0-9a-fA-F]+ invalid|giveback_to_pool|blocks are not free' "$LOG"; then
    echo "  [!] 检测到 pool 失效句柄/未释放迹象。按 references/log-keywords.md 判读,"
    echo "      并结合退出时序审查对象生命周期。"
else
    echo "  [ ] 未发现典型 CMM 错误或内存不足关键字。若现象仍疑似内存问题,"
    echo "      按 references/log-capture-guide.md 补抓日志,或查看 /proc/ax_proc/mempool 确认 FreeCnt。"
fi
