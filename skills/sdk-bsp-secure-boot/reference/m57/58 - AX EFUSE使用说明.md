eFuse bit说明

本章节包含：

1.1 eFuse说明

1.2 私有区域

1.3 Anti rollback区域

1.4 Bondoption区域

1.5 Root Key区域

1.6 Public key hash区域

1.7 BLK LOCK区域

1.8 HSM OTP区域

1.9 FEK区域

1.10 用户区域

eFuse说明

AX637上有两个eFuse控制器，每个eFuse总共有2Kbit，分为64个blk，每个blk有32bit。部分eFuse已经规划使用，用户不可随意烧写。eFuse0对应blk0~blk63，eFuse1对应blk64~blk127。

私有区域

blk0~5和blk124~125这部分区域为爱芯芯片出厂预烧写好，用户不可操作。其中芯片的unique ID就烧写在blk0~blk1区域，共64bit。在linux下可以通过下面命令获取unique ID：

cat /proc/ax_proc/hwinfo/uid

Anti rollback区域

blk6~13这部分区域规划为anti rollback区域，用于给用户烧写各个启动镜像的基础版本。如果使能anti rollback功能，启动时会校验当前程序版本和eFuse中基础版本比较。每个eFuse blk对应一个启动镜像版本。

| Blk | rollback version image |
| --- | --- |
| 6 | sbl version |
| 7 | rtos version |
| 8 | spl version |
| 9 | atf version |
| 10 | optee version |
| 11 | uboot version |
| 12 | kernel version |
| 13 | rootfs version |

Bondoption区域

eFuse中blk14为bondoption0，用于配置芯片属性。bondoption0和bondoption1区域的bit16~31配置属性相同，写eFuse时需要配置相同，否则会产生eFuse fcu错误。

| Bit | 属性 | 状态 | 说明 |
| --- | --- | --- | --- |
| 24 | axi iso hsk | 1:disable | 根据产品需要，决定是否关闭axi总线同步握手 |
| 23 | safety mem ecc | 1:disable | 根据产品需要，决定是否关闭safety mem ecc功能 |
| 22 | safety 24M | 1:双晶体 | 根据产品需要，当该bit为0时，由XTAL_SEL管脚决定safety和main共用一个晶体还是独立两个晶体。当该bit为1时，safety和main独立两个晶体。 |
| 21 | sec | 1:enable | 根据产品需要，决定是否使能secure属性。当使能后，safety和main的sec_glb有secure访问限制，只能secure cpu才可以访问。建议有信息安全需求时，量产时使能。 |
| 20 | bist ignore fail | 1:enable | 根据产品需要，决定是否忽略硬件mbist或lbist错误 |
| 19 | lbist | 1:enable | 根据产品需要，决定是否使能硬件lbist测试 |
| 18 | mbist | 1:enable | 根据产品需要，决定是否使能硬件mbist测试 |
| 17 | r5f tcm merge | 1:enable | 根据产品需要，决定当r5f lockstep时，是否使能tcm merge功能。当r5f split时，该bit不可使能。 |
| 16 | r5f split | 1:enable | 根据产品需要，决定是否使能两个r5f core split，默认为lockstep模式 |
| 15 | rootkey protect | 1:enable | 根据产品需要，保护eFuse中rootkey区域blk15-22只允许HSM访问，CPU不可访问。有信息安全需求时，建议使能。 |
| 14 | pkh flag0 | 1:enable | eFuse中有3个存储安全启动Public key hash区域，参考Public key hash区域解释配置。 |
| 13 | safety uart | 1:disable | 根据产品需要，决定是否关闭safety uart控制器，关闭后不可逆 |
| 12 | main emac | 1:disable | 根据产品需要，决定是否关闭main emac控制器，关闭后不可逆 |
| 11 | safety emac | 1:disable | 根据产品需要，决定是否关闭safety emac控制器，关闭后不可逆 |
| 10 | usb | 1:disable | 根据产品需要，决定是否关闭usb控制器，关闭后不可逆 |
| 7 | jtag | 1:disable | 根据产品需要，决定是否关闭jtag，关闭后不可逆 |

blk64为bondoption1，用于配置芯片属性。

| Bit | 属性 | 状态 | 说明 |
| --- | --- | --- | --- |
| 16-24 | 与bondopiton0一致 | - | 必须和bondoption0写入相同 |
| 10 | anti-rollback check | 1:enable | 当软件配置使能防回滚功能时，如果该bit使能，则会进行防回滚校验。SDK软件会自动写入该bit，无需客户操作。 |
| 9 | download usb | 1:disable | 根据产品需要，决定是否关闭usb download功能 |
| 8 | download sd | 1:disable | 根据产品需要，决定是否关闭sd download功能 |
| 7 | download uart | 1:disable | 根据产品需要，决定是否关闭uart download功能 |
| 6 | download can | 1:disable | 根据产品需要，决定是否关闭can download功能 |
| 4 | can6 | 1:disable | 根据产品需要，决定是否关闭can6控制器，关闭后不可逆 |
| 3 | uart1 | 1:disable | 根据产品需要，决定是否关闭uart1控制器，关闭后不可逆 |
| 2 | pkh flag1 | 1:enable | eFuse中有3个存储安全启动Public key hash区域，参考Public key hash区域解释配置。 |
| 1 | encrypt firmware | 1:enable | 使能该bit后，只接受密文的镜像启动。不使能时，可由编译配置选项控制。 |
| 0 | secure boot | 1:enable | 使能该bit后，启动时会进行安全启动校验，并校验公钥HASH。不使能时，可由编译配置选项控制。 |

Root Key区域

blk15-blk22用于存储Root Key区域，建议每个芯片烧写不同值。当bondoption0中rootkey protect使能后该区域只能够让HSM读取，建议CPU烧写后，使能bondoption0中rootkey protect确保CPU无法读出Root Key，保证Root Key无法被泄露。参考efuse_key烧写工具，进行Root Key区域烧写。

Public key hash区域

该区域用于存储安全启动RSA public key的SHA256值，确保Secure boot时校验使用的Public key不被篡改。eFuse中有3个存储安全启动Public key hash区域，用于Secure boot密钥的更新。一级Secure boot根据bondoption中的pkh flag配置决定哪个Public key hash区域生效。参考efuse_key烧写工具，进行Public key hash区域烧写。

| pkh flag0 | pkh flag1 | Public key hash生效区域 |
| --- | --- | --- |
| 0 | 0 | PKH0：blk75~blk82 |
| 0 | 1 | PKH1：blk83~blk90 |
| 1 | x | PKH2：blk23~blk30 |

BLK LOCK区域

eFuse bit只能从0写成1，并且只能写1次。如需要把整个blk锁住，需要通过写入lock bit实现。每个blk都有单独一个bit用于lock，lock bit写1后，其对应的blk中任何bit无法修改。

- Blk31中bit0~bit30用于锁住blk0~blk30

- Blk126中bit0~bit31用于锁住blk64~blk95

- Blk127中bit0~bit29用于锁住blk96~blk125

HSM OTP区域

其中blk32~blk63一共1024bit，由HSM使用，CPU不可读写，需要调用HSM接口进行操作。

FEK区域

其中blk65~blk74一个10个blk用于存储FEK(Firmware encrypt key)固件加密的Key。给启动固件加密的Key是256bit，通过Root Key AES Wrapped后一共320bit。由于每个芯片的Root key不相同，所以每个区域FEK区域存储数据也不相同。参考efuse_key烧写工具，进行FEK区域烧写。

用户区域

其他区域，blk91~blk123一共1056bit用户根据产品需求使用。

eFuse接口说明

本章节包含：

2.1 Main域用户接口

2.2 Main域TEE接口

Main域用户接口

API简介

eFuse模块Main域提供的API接口如下：

- AX_EFUSE_Init：初始化eFuse相关的软硬件资源。

- AX_EFUSE_Deinit：释放eFuse相关的软硬件资源。

- AX_EFUSE_Read：读取eFuse blk内容。

- AX_EFUSE_Write：写入eFuse blk内容。

- AX_EFUSE_Lock：对eFuse blk锁住，无法再修改。

- AX_EFUSE_Protect：对eFuse blk保护，使blk只能Secure才能访问。

API定义

AX_EFUSE_Init

【描述】

初始化eFuse模块的软硬件资源。

【语法】

AX_S32 AX_EFUSE_Init(void);

【参数】

无

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

无

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

AX_EFUSE_Deinit

【描述】

释放eFuse模块的软硬件资源。

【语法】

AX_S32 AX_EFUSE_Deinit(void);

【参数】

无

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

无

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

AX_EFUSE_Read

【描述】

读取eFuse对应blk的值

【语法】

AX_S32 AX_EFUSE_Read(AX_S32 blk, AX_S32 *data);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | eFuse blk序号0~31,64~127 | 输入 |
| data | data读取eFuse值 | 输出 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

无

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

AX_EFUSE_Write

【描述】

写入eFuse对应blk的值

【语法】

AX_S32 AX_EFUSE_Write(AX_S32 blk, AX_S32 data);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | efuse blk序号0~31,64~127 | 输入 |
| data | data写入eFuse值 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

eFuse对应bit如已写入1，不可再写1操作。

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

AX_EFUSE_Lock

【描述】

对eFuse blk锁住，无法再修改，blk中未被写1的bit也无法再写1。

【语法】

AX_S32 AX_EFUSE_Lock(AX_S32 blk);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | efuse blk序号0~30,64~125 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

eFuse blk lock后不可以回退，blk中所有bit不可修改。

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

AX_EFUSE_Protect

【描述】

对eFuse blk保护，使blk只能够Secure CPU才能够访问，Non-Secure CPU不能访问。

【语法】

AX_S32 AX_EFUSE_Protect(AX_S32 blk);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | efuse blk序号0~31,64~127 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：ax_efuse_api.h

- 库文件：libax_efuse.so

【注意】

eFuse blk protect操作非一次性操作，每次芯片启动需配置才可生效

【举例】

参考msp/sample/efuse/sample_efuse.c

【相关主题】

无

数据结构

无

错误码

eFuse API错误码如下表：

eFuse API错误码

| 错误代码 | 宏定义 | 描述 |
| --- | --- | --- |
| 0x8005000a | AX_ERR_EFUSE_ILLEGAL_PARAM | blk参数超出范围 |
| 0x80050080 | AX_ERR_EFUSE_READ_FAIL | eFuse读失败 |
| 0x80050081 | AX_ERR_EFUSE_WRITE_FAIL | eFuse写失败 |
| 0x80050082 | AX_ERR_EFUSE_LOCK_FAIL | eFuse锁失败 |
| 0x80050083 | AX_ERR_EFUSE_PROTECT_FAIL | eFuse保护失败 |

Main域TEE接口

API简介

eFuse模块Main域TEE中提供的API接口如下：

- TEE_Efuse_Read：读取eFuse blk内容。

- TEE_Efuse_Write：写入eFuse blk内容。

- TEE_Efuse_Lock：对eFuse blk锁住，无法再修改。

- TEE_Efuse_Protect：对eFuse blk保护，使blk只能Secure才能访问。

API定义

TEE_Efuse_Read

【描述】

TEE中读取eFuse对应blk的值

【语法】

TEE_Result TEE_Efuse_Read(uint32_t blk, uint32_t *data);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | eFuse blk序号0~31,64~127 | 输入 |
| data | data读取eFuse值 | 输出 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：tee_internal_api.h

【注意】

无

【举例】

参考boot/optee/optee_os-3.21.0/ta/efuse/entry.c

【相关主题】

无

TEE_Efuse_Write

【描述】

TEE中写入eFuse对应blk的值

【语法】

TEE_Result TEE_Efuse_Write(uint32_t blk, uint32_t data);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | eFuse blk序号0~31,64~127 | 输入 |
| data | data写入eFuse值 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：tee_internal_api.h

【注意】

eFuse对应bit如已写入1，不可再写1操作。

【举例】

参考boot/optee/optee_os-3.21.0/ta/efuse/entry.c

【相关主题】

无

TEE_Efuse_Lock

【描述】

TEE中对eFuse blk锁住，无法再修改，blk中未被写1的bit也无法再写1。

【语法】

TEE_Result TEE_Efuse_Lock(uint32_t blk);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | efuse blk序号0~30,64~125 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：tee_internal_api.h

【注意】

eFuse blk lock后不可以回退，blk中所有bit不可修改。

【举例】

参考boot/optee/optee_os-3.21.0/ta/efuse/entry.c

【相关主题】

无

TEE_Efuse_Protect

【描述】

TEE中对eFuse blk保护，使blk只能够Secure CPU才能够访问，Non-Secure CPU不能访问。

【语法】

TEE_Result TEE_Efuse_Protect(uint32_t blk, int enable);

【参数】

| 参数名称 | 描述 | 输入/输出 |
| --- | --- | --- |
| blk | eFuse blk序号0~31,64~127 | 输入 |
| enable | 1：控制eFuse blk保护使能<br>0：控制eFuse blk保护关闭 | 输入 |

【返回值】

| 返回值 | 描述 |
| --- | --- |
| 非0 | 失败 |
| 0 | 成功 |

【需求】

- 头文件：tee_internal_api.h

【注意】

eFuse blk protect操作非一次性操作，每次芯片启动需配置才可生效。

【举例】

参考boot/optee/optee_os-3.21.0/ta/efuse/entry.c

【相关主题】

无

数据结构

无

错误码

eFuse TEE API错误码如下表：

eFuse TEE API错误码

| 错误代码 | 宏定义 | 描述 |
| --- | --- | --- |
| 0xffff0006 | TEE_ERROR_BAD_PARAMETERS | blk参数超出范围 |
| 0xffff0000 | TEE_ERROR_GENERIC | eFuse执行错误 |

eFuse工具说明

本章节包含：

3.1 sample_efuse

3.2 sample_efuse_key

sample_efuse

工具介绍

sample_efuse工具用于对eFuse的测试工具，支持对eFuse的对应Blk读，写，锁住，保护以及整个eFuse的dump功能。

工具源码位于：msp/sample/efuse目录下。

运行帮助信息：

root@ax637r:~ # sample_efuse

./sample_efuse <type> <blk> [data]

type:

-r: read efuse blk

-w: write efuse blk

-l: lock efuse blk, can't write

-p: protect efuse blk, non-secure can't read

-d: dump efuse

-c: get chip uid from efuse

example:

./sample_efuse -r 10

./sample_efuse -w 10 0x12345678

./sample_efuse -l 10

./sample_efuse -p 10

./sample_efuse -d

./sample_efuse -c

工具使用示例

eFuse读blk

对eFuse blk4读取

root@ax637r:~ # sample_efuse -r 4

blk4: 0x5a5a5a5a

eFuse写blk

对eFuse blk91写入0xa5a5a5a5

root@ax637r:~ # sample_efuse -w 91 0xa5a5a5a5

write blk91: 0xa5a5a5a5

eFuse blk上锁

对eFuse blk91上锁

root@ax637r:~ # sample_efuse -l 91

lock blk91

eFuse blk保护

对eFuse blk91保护，保护后就无法读出blk值了

root@ax637r:~ # sample_efuse -p 91

protect blk91

root@ax637r:~ # sample_efuse -r 91

blk91: 0x0

eFuse dump操作

dump所以eFuse blk内容

root@ax637r:~ # sample_efuse -d

##[AXERA-ASLT]CASE_DATA:EFUSE:block00 = 0x00000000

##[AXERA-ASLT]CASE_DATA:EFUSE:block01 = 0x00000000

##[AXERA-ASLT]CASE_DATA:EFUSE:block02 = 0x00000000

##[AXERA-ASLT]CASE_DATA:EFUSE:block03 = 0x00000000

##[AXERA-ASLT]CASE_DATA:EFUSE:block04 = 0x5a5a5a5a

##[AXERA-ASLT]CASE_DATA:EFUSE:block05 = 0x00000000

……

sample_efuse_key

工具介绍

sample_efuse_key工具用于对eFuse中存储的key烧写，支持对Root Key，FEK，Public Key Hash，HSM HUK的烧写。

工具源码位于：msp/sample/efuse_key目录下。

运行帮助信息：

root@ax637r:~ # sample_efuse_key

./sample_efuse_key pubkey <key_idx> <pubkey_pem_file>

example: write pubkey hash to efuse

./sample_efuse_key pubkey 0 ./public.pem

./sample_efuse_key rootkey <random/static>

example: write rootkey to efuse use random or static array

./sample_efuse_key rootkey random

./sample_efuse_key rootkey static

./sample_efuse_key aeskey

example: write aeskey to efuse from static array

./sample_efuse_key aeskey

example: write hsm huk to efuse use random or static array

./sample_efuse_key hsmhuk random

./sample_efuse_key hsmhuk static

工具使用示例

为了防止eFuse中key写错，默认sample_efuse_key工具没有使能eFuse写操作。直接运行sample_efuse_key会把需要写入的key内容打印出来，默认不会直接写到eFuse中。当确认写入的key值没有错误后，可以修改msp/sample/efuse_key/efuse_key_tool.c中宏定义“EFUSE_WRITE_ENABLE”改成1，重新编译工具执行。

#define EFUSE_WRITE_ENABLE      1

Root Key烧写

通过“rootkey”参数烧写Root key。sample_efuse_key工具中Root Key的生成支持两种方式。

- random：通过HSM接口获取真随机数方式获取256bit数据作为Root Key。

- static：用户自定义的256bit数据Root Key。

通过random方式生成Root Key，写入eFuse。

【举例】

root@ax637r:~ # sample_efuse_key rootkey random

Rootkey is:

299f4e7a, 16dac513, 390f9c62,c365c3ca

0ef748be, d4eff4c2, 98ef52bf,13e9daf7

Rootkey efuse Write Success

通过static Root Key，写入eFuse。如需修改Root Key内容，修改efuse_key_tool.c中rootkey_static_array数组

static unsigned char rootkey_static_array[32] = {

0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,

0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f

};

【举例】

root@ax637r:~ # sample_efuse_key rootkey static

Rootkey is:

03020100, 07060504, 0b0a0908,0f0e0d0c

13121110, 17161514, 1b1a1918,1f1e1d1c

Rootkey efuse Write Success

通过sample_efuse_key工具烧写Root Key后，会自动使能bondoption0中bit15 rootkey protect功能，确保Root Key只能通过HSM访问。并且写过的blk会Lock住。

Public key hash烧写

通过“pubkey”参数烧写Public key hash。Public key hash有3个区域，参数中<key_idx>表示指定哪个PKH。key_idx=0~2，分别代表PKH0~2。参数<pubkey_pem_file>指定公钥pem路径。支持RSA 2048和RSA 3072 pem公钥烧写。

【举例】

烧写PKH0区域

root@ax637r:~ # sample_efuse_key pubkey 0 public.pem

RSA key is:

00 08 00 02 2b be 06 52 a2 f2 42 93 e3 33 84 d4

24 75 c5 15 66 b6 06 57 a7 f7 47 98 e8 38 89 d9

29 7a ca 1a 6b bb 0b 5c ac fc 4c 9d ed 3d 8e de

2e 7f cf 1f 70 c0 10 61 b1 01 52 a2 f2 42 93 e3

33 84 d4 24 75 c5 15 66 b6 06 57 a7 f7 47 98 e8

38 89 d9 29 7a ca 1a 6b bb 0b 5c ac fc 4c 9d ed

3d 8e de 2e 7f cf 1f 70 c0 10 61 b1 01 52 a2 f2

42 93 e3 33 84 d4 24 75 c5 15 66 b6 06 57 a7 f7

47 98 e8 38 d9 1b c8 77 27 d7 86 36 e6 95 45 f5

a4 54 04 b4 63 13 c3 72 22 d2 81 31 e1 90 40 f0

9f 4f ff ae 5e 0e be 6d 1d cd 7c 2c dc 8b 3b eb

9a 4a fa a9 59 09 b9 68 18 c8 77 27 d7 86 36 e6

95 45 f5 a4 54 04 b4 63 13 c3 72 22 d2 81 31 e1

90 40 f0 9f 4f ff ae 5e 0e be 6d 1d cd 7c 2c dc

8b 3b eb 9a 4a fa a9 59 09 b9 68 18 c8 77 27 d7

86 36 e6 95 45 f5 a4 54 04 b4 63 13 c3 72 22 d2

81 31 e1 90 20 00 01 02 01 00 01 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00 00 00 00 00 00 00 00 00 00 00 00

RSA Pubkey hash value is:

78ddfe9e, 698a9288, ccad1548,5ca04574

9f1aa945, f57eb822, b807db67,29140398

Write RSA Pubkey hash 0 Success!

同理sample_efuse_key工具烧写PKH后，对应的blk会被Lock住。

FEK烧写

通过“aeskey”参数烧写FEK（Firmware）。如需修改FEK内容，修改efuse_key_tool.c中aeskey_static_array数组

static unsigned char aeskey_static_array[32] = {

0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00

};

【举例】

root@ax637r:~ # sample_efuse_key aeskey

Aeskey is:

332ffa0d, 0f0f31d9, 971860e3,5d13963b

8e765092, 4dc93cc7, 5d30d606,7f7554c6

5dee30d7, 15336aa6

AES key efuse Write Success

同理sample_efuse_key工具烧写FEK后，对应的blk会被Lock住。

- 注意：

- 因为FEK是通过Root Key加密后写入eFuse中的，所以在烧写FEK前，先确认Root Key已经完成烧写。

HSM HUK烧写

通过“hsmhuk”参数烧写HSM HUK。HSM HUK存储在eFuse的OTP区域，只能HSM访问。sample_efuse_key工具中HSM HUK的生成支持两种方式。

- random：通过HSM接口获取真随机数方式获取256bit数据作为HSM HUK。

- static：用户自定义的128bit或256bit数据作为 HSM HUK。

通过random方式生成HSM HUK，写入HSM HUK。

【举例】

root@ax637r:~ # sample_efuse_key hsmhuk random

HSM huk Write Success

通过static HSM HUK，写入HSM OTP。如需修改HSM HUK内容，修改efuse_key_tool.c中hsmhuk_static_array数组，如需要128bit，定义16字节大小数组。

static unsigned char hsmhuk_static_array[32] = {

0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,

0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f

};

【举例】

root@ax637r:~ # sample_efuse_key hsmhuk static

HSM huk Write Success

同理sample_efuse_key工具烧写HSM HUK后，对应的blk会被Lock住。
