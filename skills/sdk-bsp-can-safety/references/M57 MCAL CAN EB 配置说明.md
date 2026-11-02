### 1. CAN MB 数量说明

目前Flexcan IP 设计上，每一路CAN 都是独立且相同的设计。每路CAN 有3块RAM 空间，这个物理空间和RX Enhance FIFO 是独立的，只给MB 使用（legecy fifo 也是使用MB，一般很少使用），每块RAM block 可以单独配置，所以总的MB 数量是根据block 配置来定的，最对支持96 MB（8 byte payload）
##### RAM block 与 MB 数量

每个 RAM block 默认对应 32 个 8 字节 MB（block 0：MB 0-31，block 1：MB 32-63，block 2：MB 64-95），由 `CAN_FDCTRL` 中对应的 `MBDSR0`/`MBDSR1`/`MBDSR2` 字段分别设置该 block 的 payload 大小：

| MBDSRn 取值 | 单个 MB payload | 该 block 可用 MB 数 |
| :---: | :---: | :---: |
| 00 | 8 字节 | 32 |
| 01 | 16 字节 | 21 |
| 10 | 32 字节 | 12 |
| 11 | 64 字节 | 7 |

寄存器字段定义以所用 FlexCAN IP 的官方参考手册为准。
### 2. CAN RX MB / Enhance FIFO 
目前CAN RX MB 和 Enhance FIFO 配置是互斥的，当使能Enhance FIFO 时， MB 不会作为接收使用，所有的MB 都作为TX MB 使用，推荐RX Enhance FIFO 模式，Enhance FIFO depth 为16 ，最多可以缓存16 帧，因为RX Enhance FIFO 可以处理多帧，减少中断数量。

### 3. CAN FD 采样点说明
CAN FD 采样点配置支持 normal CBT 和 extend CBT ,其中扩展CBT 可配置的Tq 范围更宽。根据实际需要选择是否配置扩展CBT 。

### 4. CAN RX 过滤说明
CAN RX 支持标准ID 过滤， 扩展ID 过滤， 以及标准ID 和扩展ID 混合过滤，但是混合过滤的配置中，扩展 ID 过滤器配置需要配置在前面，标准ID 过滤器配置在后面。

对于CAN 标准ID 过滤配置，数量需要配置为偶数，否则EB 会提示报错。

### 5. CAN RX DMA 说明
目前CAN RX DMA 仅支持CAN RX 配置enhance fifo 的情况，但是目前由于硬件限制，CAN RX Enhance FIFO DMA 是单帧CAN 报文触发DMA 中断，在CAN busload 较高的情况下，容易发生丢帧现象，不建议开启CAN RX Enhance FIFO DMA 功能。
