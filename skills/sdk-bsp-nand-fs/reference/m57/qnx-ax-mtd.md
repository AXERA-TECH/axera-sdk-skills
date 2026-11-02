# QNX `ax_mtd`、`mtdpart` 与 ETFS

> 本文整理自 QNX ax_mtd 知识库 v1.0及 NAND 文件系统 FAQ。实际资源名、启动脚本和参数必须以目标 QNX buildfile、SDK revision 和 board 为准。

## 设备层边界

QNX 排障必须先确认访问层：

- `ax_mtd`：提供 Axera MTD 后端及 Flash/坏块相关访问；
- `mtdpart`：基于分区元数据提供分区资源管理器；
- ETFS1/ETFS2：分别对应目标系统定义的 ETFS/裸设备路径，不能把 ETFS 设备当作连续无坏块的裸物理地址空间；
- `vspiflash`：用于特定 SPI Flash 访问链路，需确认其后端和控制器配置；
- Safety 域 NOR virtual flash、IPC/RPZC 等路径：需单独记录域、后端和调度边界。

同名分区在 Linux MTD、QNX `mtdpart` 和 ETFS 中不一定处于同一设备层，不能直接复用 Linux 的节点或性能结论。

## 分区与坏块

1. 先读取目标设备枚举和分区来源，结合 `/proc/ax_proc/mtd`、启动日志、buildfile 和生成的分区元数据确认实际布局。
2. 区分逻辑分区偏移、物理 Flash 地址、erase/page 对齐和坏块映射；坏块不能跨分区借用，也不能把示例 `/dev/mtdX` 编号当作固定接口。
3. 检查 `ax_mtd` 初始化、Flash ID/geometry、ECC、坏块扫描和 `mtdpart` 解析是否按预期完成。
4. 若读写失败，保留首次错误、设备枚举、坏块信息和调用层级；不要只依据最后的 mount 或 timeout 日志判断根因。

## ETFS1/ETFS2 与镜像

ETFS 使用 data 区和 spare/OOB 区保存文件系统信息，写入粒度通常包含 page 与 ETFS transaction。包含 ETFS transaction 的镜像不能任意按 512 字节拆分写入；烧录前必须确认镜像类型、record 大小和目标是 ETFS1 还是 ETFS2。

`/dev/etfs2` 的起始地址由分区表决定。扩大分区时需要向前调整起始位置，同时不能覆盖前置镜像；打包的 `userdata.img` 不必机械填满整个分区。调整时统一字节/KB 单位，并按 page/erase 对齐。

## 启动顺序

常见依赖是 ETFS 后端先启动，再启动 `mtdpart`；依赖 mtd 的服务还应按目标 buildfile 增加等待条件。若设备节点尚未出现就启动分区或挂载服务，应先检查启动顺序、资源管理器注册和 IPC/后端初始化，而不是立即重建文件系统。

## 性能测试

QNX `mtd` 位于 ETFS、IPC、MCAL 调度和异步路径之上，不能直接与 Linux raw MTD 的 `dd` 结果比较。测试应记录：设备层、分区、数据量、读/写/擦除策略、命令、调度配置和 `time` 结果，并与相同数据量、相同介质状态的基线比较。`mtd_debug` 或 SDK 对应工具只说明指定层级的表现。

## 验证清单

- `ax_mtd` 后端和 Flash geometry；
- `/proc/ax_proc/mtd`、分区元数据和实际设备节点；
- ETFS1/ETFS2 类型、record/page/erase 对齐；
- 坏块扫描与逻辑映射；
- buildfile 启动顺序和依赖等待；
- 挂载日志、读写回读和掉电/重启后状态。

## 来源

- QNX ax_mtd 知识库 v1.0。
- nand 文件系统 FAQ。
