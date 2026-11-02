# M57 Security 开发指南

**文档版本：V1.0**

**发布日期：2025/11/12**

权利声明

本文档版权归爱芯元智（AXERA）所有，按本仓库根目录 LICENSE 所述的 MIT 许可提供。

注意

您购买的产品、服务或特性等应受商业合同和条款的约束，本文档中描述的全部或部分产品、服务或特性可能不在您的购买或使用范围之内。除非商业合同另有约定，本公司对本文档内容不做任何明示或默示的声明或保证。

由于产品版本升级或其他原因，本文档内容会不定期进行更新。除非另有约定，本文档仅作为使用指导，本文档中的所有陈述、信息和建议不构成任何明示或暗示的担保。

# 前言

**适用产品**

M57

**适读人群**

 软件开发工程师

 技术支持工程师

**符号与格式定义**

| 符号/格式 | 说明 |
| --- | --- |
| xxx | 表示您可以执行的命令行。 |
| *斜体* | 表示变量。如，“*安装目录*/M57_SDK_Vx.x.x/build目录”中的“安装目录”是一个变量，由您的实际环境决定。 |
| **说明/备注：** | 表示您在使用产品的过程中，我们向您说明的事项。 |
| **注意：** | 表示您在使用产品的过程中，需要您特别注意的事项。 |

# 修订历史

| 文档版本 | 发布时间 | 修订说明 |
| --- | --- | --- |
| V0.5 | 2025/07/30 | 文档初版 |
| V0.6 | 2025/10/14 | 更新Secure Access,Secure Storage,Secure Update,Key Management,Lifecycle |
| V1.0 | 2025/11/12 | 增加安全启动失败信息收集 |

# 1 概述

## 1.1 Security方案内容

本文档主要介绍基于M57平台构建安全可信环境，Security方案主要涉及如下8个主要内容：

1. Secure Boot；
2. TEE使用
3. Secure Debug
4. Secure Access
5. Secure Storage
6. Secure Update
7. Key Management
8. Lifecycle

# 2 SecureBoot

## 2.1 M57 Secure boot概述

M57支持安全启动功能，防止非法篡改启动镜像，使能 Secure Boot 后，会对启动镜像进行校验，M57芯片的secureboot流程如下：

图2-1 安全启动流程

如上图，M57在开启secureboot时，安全启动分为几个阶段：

1. BootRom安全启动阶段：BootRom加载并校验SBL，R5F跳转SBL。
2. SBL安全启动阶段：SBL加载并校验SPL，A55跳转SPL。SBL加载并校验AutoSAR/RTOS，R5F跳转AutoSAR/RTOS。
3. SPL安全启动阶段：SPL加载并校验ATF，OPTEE，UBOOT，A55跳转ATF。
4. UBOOT安全启动阶段：UBOOT加载并校验Kernel镜像，UBOOT校验ROOTFS root hash的签名。A55跳转Kernel。
5. ROOTFS dm-verity校验：读取rootfs镜像和rootfs hash tree完成校验。

M57安全启动支持如下特性：

1. 支持对签名RSA公钥合法性校验。
2. 支持RSA密钥更新。
3. 支持RSA-2048/3072算法可配。
4. 支持密文固件启动。
5. 整个安全启动链，调用硬件HSM加速解密和验签。

### 2.1.1 BootRom安全启动阶段

M57芯片BootRom中启动下一级启动镜像SBL，决定是否启用Secure Boot流程，由 eFuse 中的 Bond Option 与编译 SBL 时添加的 image header 共同决定。SBL的image header总共固定1.5KB大小，其中会记录SBL镜像的信息，包含镜像长度，RSA签名，RSA公钥等。header的信息大致如下：

```
struct img_header{
    u32 check_sum;//0x00
    u32 magic_data;//0x04, should be 0x55543322
    u32 capability;
    u32 img_size;
    u32 img_check_sum;
    ……
    u32 security_attr;
    ……
    /* location is 512 byte */
    /* rsa public key info */
    u32 key_n_header;
    u32 rsa_key_n[96];
    u32 key_e_header;
    u32 rsa_key_e;
    /* sbl rsa signature info */
    u32 sig_header;
    u32 signature[96];
};
```
其中security_attr标记和sbl安全相关的属性。编译sbl时根据软件配置使能。

| security_attr bit | 详细说明 |
| --- | --- |
| bit0 | 0：使用 RSA-2048 签名；1：使用 RSA-3072 签名 |
| bit1 | 0：不启用 Secure Boot；1：启用 Secure Boot。 |
| bit2 | 0:打包的sbl是明文镜像，1：打包的sbl镜像是密文镜像像。 |

SBL镜像通过build/scripts/imgsign/sbl_sign.py完成签名打包。BootROM 会加载 HSM 固件。SDK中的HSM固件已经是一个被Axera密钥加密签名过的软件固件。SBL镜像签名打包过程如下：

图2-2 SBL签名打包过程

SBL镜像通过build/scripts/imgsign/img_aes.py完成镜像加密。SBL镜像AES加密过程如下：

图2-3 SBL加密过程

BootRom会使用SBL的image header中的RSA public key进行RSA verify。为了确保SBL的image header中的RSA public key是一个合法的值，在eFuse中留有了三个Public key hash区域，用于提前烧写RSA public key的sha256值。BootRom中会对image header中的RSA public key计算sha256值和eFuse中Public key hash区域值比较。Public key hash校验成功则表明公钥是合法的。

eFuse中bondoption相关配置参考《AX EFUSE使用说明》文档，那么在BootRom中Secure boot执行的流程根据eFuse bondoption和image header中security_attr共同决定。BootROM中Secure boot流程如下：

图2-4 BootRom Secure boot流程

BootRom中如果加载的SBL镜像是密文镜像，会调用HSM获取eFuse中的密钥进行解密。镜像使用的加密模式是AES-ECB，key的长度是256bit。镜像解密过程如下：

图2-5 BootRom image decrypt流程

BootRom中使能Secure boot遵循的原则：

1. eFuse中使能Secure boot必会走Secure boot流程，且会校验image header中的RSA public key。
2. 如果eFuse中Secure boot未使能，由image header中security_attr决定是否走Secure boot流程，但不会校验image header中的RSA public key。
3. eFuse中encrypt firmware使能，只能烧写密文的SBL镜像。且eFuse中的RTK和FEK需要提前正确烧写。
4. 使能Secure boot后，BootRom会先加载HSM固件，HSM的Rom会对HSM固件进行安全启动校验。

### 2.1.2 SBL安全启动阶段

SBL阶段会引导下一级启动镜像SPL和AutoSAR/RTOS启动。安全启动流程与 BootROM 中一致。SBL阶段无需重复加载HSM固件，在BootRom阶段已经完成HSM固件的加载。SPL镜像和AutoSAR/RTOS通过build/scripts/imgsign/img_sign.py完成签名打包。镜像签名打包过程如下：

图2-6 SPL/AutoSAR/RTOS签名打包过程

### 2.1.3 SPL安全启动阶段

SPL负责加载并校验ATF，OPTEE，UBOOT启动镜像。SPL使用uboot开源组件中自带的FIT安全启动校验方式。FIT(Flattened Image Tree)启动方案，会把启动镜像通过dts的语法编译一个镜像文件。每个启动镜像在编译时会生成对应的its文件，用于描述启动该镜像的属性，其中包含安全启动相关属性。制作FIT镜像需要两个工具，mkimage和dtc。

图2-7 FIT Image 签名打包过程

在ATF，OPTEE，UBOOT中编译时通过build/scripts/generate_its.py脚本生成各个镜像的its文件。its文件用于描述启动该镜像的属性，其中包含安全启动相关属性。its遵循dts语法，格式如下：

```
/dts-v1/;
/ {
    description = "component image description";
    #address-cells = <2>;
    images {
        firmware-1 {
            data = /incbin/("path/to/data/xx.bin");
            description = "component image description";
            type = "image type name";
            arch = "arm64";
            compression = "none";
            load = <0x1 0x04000000>;
            entry = <0x1 0x04000000>;
            os = "OS name";
            hash-1 {
                algo = "sha256";
            };
        };
    };
    configurations {
        default = "conf-1";
        conf-1 {
            description = "component image description";
            firmware = "firmware-1";
            loadables = "firmware-1";
            signature {
                sign-images = "firmware";
                algo = "sha256,rsa2048";
                key-name-hint = "akcipher2048";
            };
        };
   };
};
```
its中‘/images’ node描述了Image的必要信息

| Property | Description |
| --- | --- |
| description | 镜像的文本描述 |
| type | 镜像的类型，比如 kernel、firmware |
| data | 该节点二进制文件的路径 |
| compression | 压缩方式，比如none、gzip 等 |
| os | 操作系统的名称，比如 U-Boot、TEE 等 |
| arch | 平台架构，比如arm64 |
| entry | 二进制文件入口地址，即链接地址 |
| load | 二进制文件的加载地址 |
| hash-1 | 镜像使用的校验算法，比如sha256、crc32 等 |

‘/configurations’ node描述了Image的配置信息

| **Property** | **Description** |
| --- | --- |
| default | 默认的子节点配置 |
| conf-1 | 描述具体使用哪些镜像 |
| description | 该配置的名称 |
| firmware | 该firmware的名称 |
| loadables | 额外的可加载的二进制文件的列表，U-Boot将在给定的起始地址加载每个二进制文件 |
| signature | 描述签名的配置信息<br>sign-images：对/images node中指定的image node做签名。<br>algo：签名算法<br>key-name-hint：指定的密钥名称 |

使用mkimage工具制作时，会根据its中配置生成/images下镜像的校验值和指定的image node和conf中属性的签名，填充到对应的node中value属性。

那么FIT安全启动签名过程是：

1. 对image的二进制文件计算hash值，保存在its中image node的hash node下。
2. 根据its中configurations node中的sign-images的配置，计算对应的image node和 configurations node中属性的签名，保存在signature node下。

图2-8 FIT Image 签名过程

FIT带签名的镜像实则就是一个dtb文件，可以通过fdtdump工具把文件展开。以ATF镜像为例：

```
$fdtdump bl31_signed.img
/ {
    timestamp = <0x686e1f39>;
    description = "ARM Trusted Firmware";
    #address-cells = <0x00000002>;
    images {
        firmware-1 {
            data = [f4 03 00 aa f5 03 01 aa f6 03 02 aa f7 03 03 aa 80 bf 03 10 00 c0 1e d5 df 3f 03 d5 3b 15 00 94 41 01 82 d2 00 10 3e d5 00 00 01 aa 00 10 1e d5 df 3f 03 d5 16 16 00 94 00 47 80 d2 00 11 1e d5 00 00 ……];
            description = "ARM Trusted Firmware";
            type = "firmware";
            arch = "arm64";
            compression = "none";
            load = <0x00000001 0x00104000>;
            entry = <0x00000001 0x00104000>;
            os = "arm-trusted-firmware";
            hash-1 {
                value = <0xb9f02efe 0xf1f1b1cd 0x54bb9bd5 0x6e0154e2 0xd23270e9 0xf89a4a1c 0x17b1de32 0xc6f4376d>;
                algo = "sha256";
            };
        };
    };
    configurations {
        default = "conf-1";
        conf-1 {
            description = "ARM Trusted Firmware";
            firmware = "firmware-1";
            loadables = "firmware-1";
            signature {
                hashed-strings = <0x00000000 0x0000008e>;
                hashed-nodes = "/", "/configurations/conf-1", "/images/firmware-1", "/images/firmware-1/hash-1";
                timestamp = <0x686e1f39>;
                signer-version = "2022.10-g3e2360d7-dirty";
                signer-name = "mkimage";
                value = <0x05d6eb09 0xedbbd5ce 0xce177fc0 0x6b27c0df 0xa7e75472 0x2c8380d2 0xbdceb87d 0x21cd04ae 0x0569cfab 0x72c1afdc 0x43b59966 0x8e77570f 0xc2d0fc25 0xd4cdc66f 0xc49a02ff 0x57c69372 0x6a0afe8f 0x6c23224a 0x489fa912 0xa30e2e0d 0xeae3575e 0xb6cb4ca2 0x6329b4ec 0x43d8664e 0xc5357734 0x764e6a35 0x66a7d307 0x4048e57c 0xac8889cd 0x5edc7ecc 0x291b20d4 0x86142d5d 0x44aa73be 0xf8fe30c2 0x9a2f7feb 0xf32371d9 0xda505a6e 0xd65e0dff 0x7e1c0ee0 0x8eda69d4 0x8673bba8 0xc3a43b3e 0xc1d77033 0x92a042aa 0xea2bc432 0x961eec3c 0xe58ddd8d 0x24c1ed87 0x3396b2b6 0xdab801c3 0xd2e6fe82 0x200447eb 0x9848ac29 0x4ee86235 0xb77cf143 0xc3cdef66 0x17a8b74a 0x0608ce65 0x76b82961 0xbe4ed51a 0x8401f6ac 0x38667caf 0xebb31fde 0x144abe59>;
                sign-images = "firmware";
                algo = "sha256,rsa2048";
                key-name-hint = "akcipher2048";
            };
        };
    };
};
```
从上面例子可以看出镜像元数据会拷贝到/images/firmware-1/ node的data属性中。并且会把镜像计算sha256值拷贝到/images/firmware-1/hash-1 node下。从/configurations/conf-1/signature node中hashed-nodes属性中配置的node计算sha256并rsa2048计算签名，会把签名数据拷贝到/configurations/conf-1/signature node中value属性中。

在设备上FIT安全启动校验过程是：

1. 先读取存储带签名镜像，签名镜像满足设备树格式，获取configurations node中signature node下的签名，并对configurations node中的hashed-nodes的配置中的image node和 configurations node进行hash计算并签名验证。验签的公钥使用当前运行程序设备树中存储的公钥。
2. itb中image node验签通过，确保加载镜像的校验sha256值正确。再读取二进制image，并计算hash值和itb中image node中sha256值进行比较，确保数据没有被篡改。

图2-9 FIT Image 验签过程

在SPL的dtb中会记录公钥的相关信息，在安全启动使能后，RSA公钥会从自身的dtb中获取公钥信息。SPL的公钥示例如下，可以通过工具生成：

```
signature {
        required-mode = "any";
        key-akcipher2048 {
            required = "conf";
            algo = "sha256,rsa2048";
            rsa,r-squared = <0x37eed719 0xdb673ba7 0x0f13e3f4 0x61b949f5 0x3e4a5cb9 0x9d08ecd4 0x9b7a0f15 0x59126426 0x2de5477d 0xaa28ec67 0xc80eaf52 0xddba5fda 0x42c3767d 0xb93877d6 0x2d420a5c 0x9a853363 0xc19ccea0 0x243a7671 0x93e90e4a 0xc1c71306 0x6a9048a2 0x9eb8d3e6 0xbf85e89a 0xaa1fb154 0x635d0bb7 0xf8cacac3 0xf6c00a0d 0xe630b06b 0xacfaddcd 0xcebfb86f 0x55a8de8e 0xb6f4566e 0xa347c522 0x8f78c0e2 0xc9a6596e 0x4430dc32 0xd95921fd 0xb907f040 0x9c95d639 0xf16131cb 0xb6723d08 0x4f799a89 0xa065de64 0xf4397409 0x1cfb21df 0x99f11376 0x35dfc2c0 0x5bba1ece 0x03c1f832 0x4b7c63bc 0x525e0216 0x707a2eb7 0x36071cea 0x9d36291e 0xfc2b22ef 0xaa7d82dc 0x6a3bcd7e 0x278ea94d 0xde1b1b9e 0x4e7c0023 0xfa62f13e 0xb35ad261 0x2a821f6c 0x27282947>;
            rsa,modulus = <0x90e13181 0xd22272c3 0x1363b404 0x54a4f545 0x95e63686 0xd72777c8 0x1868b909 0x59a9fa4a 0x9aeb3b8b 0xdc2c7ccd 0x1d6dbe0e 0x5eaeff4f 0x9ff04090 0xe13181d2 0x2272c313 0x63b40454 0xa4f54595 0xe63686d7 0x2777c818 0x68b90959 0xa9fa4a9a 0xeb3b8bdc 0x2c7ccd1d 0x6dbe0e5e 0xaeff4f9f 0xf04090e1 0x3181d222 0x72c31363 0xb40454a4 0xf54595e6 0x3686d727 0x77c81bd9 0x38e89847 0xf7a75706 0xb66615c5 0x7524d484 0x33e39342 0xf2a25201 0xb16110c0 0x701fcf7f 0x2ede8e3d 0xed9d4cfc 0xac5c0bbb 0x6b1aca7a 0x29d98938 0xe89847f7 0xa75706b6 0x6615c575 0x24d48433 0xe39342f2 0xa25201b1 0x6110c070 0x1fcf7f2e 0xde8e3ded 0x9d4cfcac 0x5c0bbb6b 0x1aca7a29 0xd98938e8 0x9847f7a7 0x5706b666 0x15c57524 0xd48433e3 0x9342f2a2 0x5206be2b>;
rsa,exponent = <0x00000000 0x00010001>;
rsa,n0-inverse = <0x3b01ef7d>;
rsa,num-bits = <0x00000800>;
            key-name-hint = "akcipher2048";
        };
    };
```
如果 ATF、OP-TEE 或 U-Boot 使用加密镜像，且已使能加密镜像配置在编译时会调用mkimage工具完成加密，加密算法采用AES-CBC模式，key的长度是256bit。

图2-10 FIT加密过程

通过build/scripts/generate_its.py脚本生成各个镜像的enc.its文件。enc.its文件比只签名的its中增加一个cipher node，用于描述对称加密的算法和加密初始化向量IV。enc.its增加格式如下：

```
/dts-v1/;
/ {
    images {
        firmware-1 {
            cipher {
                 algo = "aes256";
                 key-name-hint = "dev";
                 iv = <0xce08be2e 0xd37dd692 0x5d495eff 0x144acc84>;
            };
        };
    };
```
其中iv会在每次编译时随机生成，并且会把明文镜像加密后填充到/images/firmware-1/ node的data属性。

在设备中对密文镜像像解密过程和SBL中类似，AES的Key是从eFuse中获取。密文数据和AES IV是从加密镜像中获取。解密过程如下：

图2-11 FIT解密过程

### 2.1.4 UBOOT安全启动阶段

UBOOT负责引导和校验KERNEL启动和对ROOTFS的Root hash签名校验。对KERNEL的安全启动校验过程及解密过程和SPL阶段使用FIT方案一致，包含kernel启动配置文件extlinux.conf和带签名的Image.sign kernel镜像。下面是kernel的签名过程：

图2-12 Kernel签名过程

ROOTFS编译的时候如果使能ROOTFS_DMVERITY配置，则会调用veritysetup工具计算出ROOTFS的hash tree和Root hash。然后在调用rootfs_sign.py脚本完成对Root hash的签名。ROOTFS的签名过程如下：

图2-13 ROOTFS签名过程

在设备UBOOT启动阶段会获取ROOTFS的镜像类型和计算出ROOTFS原镜像的大小从而获取出Root hash和Root hash的签名数据。使用UBOOT自身设备树中的公钥完成签名的校验。验签通过后，解析 root hash 中的内容，设置dm-mod.create参数通过bootargs传递给kernel。ROOTFS的Root hash验签过程如下：

图2-14 ROOTFS Root hash验签过程

### 2.1.5 ROOTFS dm-verity校验

U-Boot 会校验 rootfs 的 Root hash 签名，但不会在 U-Boot 中将完整的 rootfs 镜像读出。Dm-verity机制目前是确保rootfs的安全启动，从而形成一套完整的安全启动方案。rootfs分区相比其他boot分区会大很多，如果对整个分区进行hash运算，完整镜像读到内存中，需要占用较大内存，并且对整个镜像hash运算，需要消耗较长时间。

dm-verity 依靠内核提供的device mapper 机制，验证rootfs分区hash tree 数据。验证通过后，在设备节点上添加dm-verity 设备。以后任何对rootfs分区上数据的操作，都会映射到dm-verity 设备节点上，首先对待操作数据所在的block 计算一次hash，将此hash值与该block 在初始hash tree 中对应的hash 进行对比，一旦对比失败，dm-verity 就会返回失败给此次操作的调用者。Hash tree形成过程如下：

图2-15 ROOTFS dm-verity Hash tree过程

如上图hash tree，确保每个block不被篡改，首先得保证hash tree不被修改，那么只需root hash不被篡改。dm-verity方案中对root hash进行数字签名，启动时会首先对root hash镜像签名校验。

使用dm-verity方案，确保rootfs分区文件系统是一个只读的文件系统，目前rootfs支持dm-verity使用squashfs和ext4只读文件系统。ROOTFS dm-verity校验过程如下：

图2-16 ROOTFS dm-verity 校验过程

## 2.2 Secure boot方案实施

### 2.2.1 安全启动密钥管理

#### 1. 准备一对RSA密钥对

-- 生成 RSA 私钥（传统格式的）

```
openssl genrsa -out private_key.pem 2048（或 3072）
```
-- 生成 RSA 公钥

```
openssl rsa -in private_key.pem -pubout-RSAPublicKey_out -out public_key.pem
```
用自己的密钥替换{SDK}\tools\imgsign目录下的公私密钥。如下：

| RSA密钥长度 | 私钥路径 | 公钥路径 |
| --- | --- | --- |
| RSA-2048 | tools/imgsign/private.pem | tools/imgsign/public.pem |
| RSA-3072 | tools/imgsign/key_3072/private.pem | tools/imgsign/key_3072/pubkey.pem |

#### 2. 准备对称密钥AES Key

AES Key 以文本形式存放在 {SDK}\tools\imgsign\aes-256.key 中，用户可以自定义或通过随机数生成 AES Key。例如，生成 32 字节随机数作为 Key。把生成的内容拷贝到{SDK}\tools\imgsign\aes-256.key文本中。

```
$ openssl rand -hex 32
3cb0cb4afe91593ec6d0a23719de9885bd10c6bb20c22b21d62fca1f10a26f83
```
#### 3. eFuse密钥烧写

建议先阅读《AX EFUSE使用说明》文档，先了解规划的密钥区域和烧写方法。

-- Root Key烧写

Root Key需先烧写，建议不同芯片烧写唯一且不同的值。使用sample_efuse_key工具烧写方法参考《AX EFUSE使用说明》3.2.2 Root Key烧写章节。Root Key烧写后，CPU无法读出。

-- Public key hash烧写

建议产品生产阶段生成三组不同的 RSA 密钥对，把三个PKH区域都烧写上，产品中根据需要烧写eFuse的bondoption选择不同的PKH。调试阶段可根据需求烧写，烧写方法参考《AX EFUSE使用说明》3.2.2 Public key hash烧写章节。

-- FEK烧写

如果不需要启动镜像密文，则FEK不需要烧写。FEK是AES Key根据Root Key加密处理过的数据，所以如果Root Key不一样则烧写后的FEK区域值也不一样。烧写方法参考《AX EFUSE使用说明》3.2.2 FEK烧写章节。

#### 4. uboot中公钥替换

在SPL和UBOOT阶段所使用的公钥是自身dtb中的公钥，所以不受eFuse的限制。但是需要把公钥的参数拷贝到uboot源码的dts中。

-- 解析公钥参数

使用build/scripts/extract_pkey_param.py脚本完成公钥参数解析，例如：

```
$ python3 build/scripts/extract_pkey_param.py -k tools/imgsign/public.pem
Public Key Filename: tools/imgsign/public.pem
Public Key Parameters:
rsa,r-squared = <0x37eed719 0xdb673ba7 0x0f13e3f4 0x61b949f5
                 0x3e4a5cb9 0x9d08ecd4 0x9b7a0f15 0x59126426
                 0x2de5477d 0xaa28ec67 0xc80eaf52 0xddba5fda
                 0x42c3767d 0xb93877d6 0x2d420a5c 0x9a853363
                 0xc19ccea0 0x243a7671 0x93e90e4a 0xc1c71306
                 0x6a9048a2 0x9eb8d3e6 0xbf85e89a 0xaa1fb154
                 0x635d0bb7 0xf8cacac3 0xf6c00a0d 0xe630b06b
                 0xacfaddcd 0xcebfb86f 0x55a8de8e 0xb6f4566e
                 0xa347c522 0x8f78c0e2 0xc9a6596e 0x4430dc32
                 0xd95921fd 0xb907f040 0x9c95d639 0xf16131cb
                 0xb6723d08 0x4f799a89 0xa065de64 0xf4397409
                 0x1cfb21df 0x99f11376 0x35dfc2c0 0x5bba1ece
                 0x03c1f832 0x4b7c63bc 0x525e0216 0x707a2eb7
                 0x36071cea 0x9d36291e 0xfc2b22ef 0xaa7d82dc
                 0x6a3bcd7e 0x278ea94d 0xde1b1b9e 0x4e7c0023
                 0xfa62f13e 0xb35ad261 0x2a821f6c 0x27282947>;
rsa,modulus = <0x90e13181 0xd22272c3 0x1363b404 0x54a4f545
               0x95e63686 0xd72777c8 0x1868b909 0x59a9fa4a
               0x9aeb3b8b 0xdc2c7ccd 0x1d6dbe0e 0x5eaeff4f
               0x9ff04090 0xe13181d2 0x2272c313 0x63b40454
               0xa4f54595 0xe63686d7 0x2777c818 0x68b90959
               0xa9fa4a9a 0xeb3b8bdc 0x2c7ccd1d 0x6dbe0e5e
               0xaeff4f9f 0xf04090e1 0x3181d222 0x72c31363
               0xb40454a4 0xf54595e6 0x3686d727 0x77c81bd9
               0x38e89847 0xf7a75706 0xb66615c5 0x7524d484
               0x33e39342 0xf2a25201 0xb16110c0 0x701fcf7f
               0x2ede8e3d 0xed9d4cfc 0xac5c0bbb 0x6b1aca7a
               0x29d98938 0xe89847f7 0xa75706b6 0x6615c575
               0x24d48433 0xe39342f2 0xa25201b1 0x6110c070
               0x1fcf7f2e 0xde8e3ded 0x9d4cfcac 0x5c0bbb6b
               0x1aca7a29 0xd98938e8 0x9847f7a7 0x5706b666
               0x15c57524 0xd48433e3 0x9342f2a2 0x5206be2b>;
rsa,exponent = <0x00000000 0x00010001>;
rsa,num-bits = <0x00000800>;
rsa,n0-inverse = <0x3b01ef7d>;
```
U-Boot 的 DTS 中公钥保存在 boot/uboot/u-boot-2022.10/arch/arm/dts/m57h-keys.dtsi文件中。注意RSA2048公钥替换m57h-keys.dtsi中key-akcipher2048 node，RSA3072公钥替换m57h-keys.dtsi中key-akcipher3072 node。

### 2.2.2 安全启动配置

默认配置中安全启动是不使能的，需要用户根据需求配置。安全启动的配置都在build/platforms下的配置，例如build/platforms/axera/demo_nor_nand/config.mk配置：

```
# SECURE_BOOT: Secure boot flag (TRUE/FALSE)
# Set to TRUE to compile and build secure boot images and package them.
SECURE_BOOT           := FALSE
# ENABLE_CIPHER: Flag to indicate whether cipher support is enabled.
# Setting it to TRUE enables the cipher, while setting it to FALSE disables it.
ENABLE_CIPHER         := FALSE
# ROOTFS_DMVERITY: rootfs dm-verity flag (TRUE/FALSE)
# Set to TRUE to compile and build secure boot rootfs images and package them.
ROOTFS_DMVERITY       := FALSE
# SIGN_USE_RSA3072: Use RSA3072 key for signing (TRUE/FALSE)
# Set to TRUE to use RSA3072 key for signing images, otherwise RSA2048 key will be used.
SIGN_USE_RSA3072     := FALSE
# ROOTFS_FS_TYPE: Rootfs filesystem type
# Possible values: UBI, EXT4, SQUASH, etc.
ROOTFS_FS_TYPE       := UBI
```
其中使能ENABLE_CIPHER和ROOTFS_DMVERITY配置前提是要使能SECURE_BOOT配置。对于不同配置编译后生成镜像名称如下：

| 镜像名称 | SECURE_BOOT:=FALSE | SECURE_BOOT:=TRUE | ENABLE_CIPHER:=TRUE |
| --- | --- | --- | --- |
| SBL | sbl_signed.img | sbl_signed.img | sbl_enc_signed.img |
| Autosar/RTOS | Mcal_Demo_signed.img | Mcal_Demo_signed.img | Mcal_Demo_enc_signed.img |
| SPL | u-boot-spl_signed.img | u-boot-spl_signed.img | u-boot-spl_enc_signed.img |
| UBOOT | u-boot.img | u-boot_signed.img | u-boot_enc_signed.img |
| ATF | bl31.img | bl31_signed.img | bl31_enc_signed.img |
| OPTEE | optee.img | optee_signed.img | optee_enc_signed.img |
| KERNEL | kernel.img | kernel_signed.img | kernel_enc_signed.img |

ROOTFS镜像不支持密文，所以ROOTFS针对ROOTFS_DMVERITY配置编译生成的镜像不同。并且如果ROOTFS_DMVERITY使能后，ROOTFS_FS_TYPE只能配置成EXT4或SQUASH。

| 镜像名称 | ROOTFS_DMVERITY:=FALSE | ROOTFS_DMVERITY:=TRUE |
| --- | --- | --- |
| ROOTFS | rootfs.img | rootfs_signed.img |

SIGN_USE_RSA3072可配置使用RSA2048还是RSA3072密钥。

### 2.2.3 安全启动注意事项

1. eFuse不烧写，也可以运行软件配置SECURE_BOOT使能的镜像，设备启动也会对Secure boot校验。建议烧写eFuse前，先使能软件配置SECURE_BOOT，使整个启动流程跑通。
2. eFuse中使能Secure boot必会走Secure boot流程，且会校验eFuse中PKH，无法运行不带正确签名的镜像。
3. 运行对称加密的镜像，提前必须要正确烧写RootKey和FEK。
4. 妥善保管生成的密钥，防止泄露或丢失，否则会造成安全启动功能失效。

### 2.2.4 安全启动失败事件收集

各启动阶段的安全启动失败事件会汇总到相应接口，用户可根据需求记录，并获取当前安全启动校验失败的分区。

| 安全启动阶段 | 接口 | 路径 |
| --- | --- | --- |
| SBL | set_secureboot_failed() | SafetyIsland/sbl/boot/boot.c |
| SPL | board_pre_hang() | uboot/u-boot-2022.10/arch/arm/mach-axera/m57/fault.c |
| UBOOT |  |  |

SPL 和 U-Boot 启动过程中的异常信息均汇总到 board_pre_hang() 接口。可以在这个接口中获取到镜像类型以及错误原因。

| 字段信息 | 意义 |
| --- | --- |
| fault_id[23:0] | 标识各级的错误类型，每个BIT代表一种错误。安全启动失败属于FAULT_ILLEGAL_IMAGE错误类型。<br>enum fault_code {<br>/* fault happen when loading image */<br>FAULT_LOAD_IMAGE      = 0x1,<br>/* corrupted image */<br>FAULT_ILLEGAL_IMAGE   = 0x2,<br>/* boot initialization failure */<br>FAULT_INIT_FAILURE    = 0x4,<br>}; |
| fault_id[31:24] | 标识当前的镜像类型，比如SPL， ATF， OPTEE和U-Boot等，每个BIT代表一种镜像<br>enum fault_boot_stage {<br>FAULT_BS_SBL    = 0x01,<br>FAULT_BS_SPL    = 0x02,<br>FAULT_BS_RTOS   = 0x04,<br>FAULT_BS_ATF    = 0x08,<br>FAULT_BS_OPTEE  = 0x10,<br>FAULT_BS_UBOOT  = 0x20,<br>FAULT_BS_KERNEL = 0x40,<br>}; |
| fault_reason[23:0] | 表示安全启动失败，校验下一级镜像类型，每个BIT代表一种镜像<br>enum fault_image_type {<br>FAULT_IMAGE_TYPE_UNKNOWN = 0x0,<br>FAULT_IMAGE_TYPE_ATF     = 0x4,<br>FAULT_IMAGE_TYPE_OPTEE   = 0x8,<br>FAULT_IMAGE_TYPE_UBOOT   = 0x10,<br>FAULT_IMAGE_TYPE_KERNEL  = 0x20,<br>FAULT_IMAGE_TYPE_ROOTFS  = 0x40,<br>}; |
| fault_reason[31:24] | 校验失败slot信息。0：SLOTA，1：SLOTB |

# 3 TEE使用

## 3.1 TEE概述

M57支持Trustzone，在Main域使用Optee方案，Trusted Execution Environment （TEE）提供一个可信的软件执行环境，分为两个运行世界，分别是Normal World和Secure World。Normal World和Secure World之间可通过Firewall隔离，使运行在 Normal World 中的软件（如 U-Boot 或 Linux）无法访问 TEE 资源。TEE下负责执行一些安全操作，例如安全加解密，认证，密钥管理等。

图3-1 TEE架构图

## 3.2 TEE配置

默认配置中TEE是使能的，TEE的配置使能在build/platforms下的配置，例如build/platforms/axera/demo_nor_nand/config.mk配置：

```
# SUPPORT_ATF: Flag to indicate whether ARM Trusted Firmware (ATF) support is enabled.
# Possible values: TRUE, FALSE
SUPPORT_ATF          := TRUE
# SUPPORT_OPTEE: Flag to indicate whether OP-TEE support is enabled.
# Possible values: TRUE, FALSE
SUPPORT_OPTEE        := TRUE
```
optee的配置位于boot/optee/optee_os-3.21.0/core/arch/arm/plat-axera/conf.mk中

```
ifneq ($(PLAT_OPTEE_ADDR_START),)
core-platform-cppflags += -DTZDRAM_BASE="$(PLAT_OPTEE_ADDR_START)"
else
core-platform-cppflags += -DTZDRAM_BASE=0x104000000
endif
ifneq ($(PLAT_OPTEE_SHMEM_SIZE),)
core-platform-cppflags += -DTEE_SHMEM_SIZE="$(PLAT_OPTEE_SHMEM_SIZE)"
else
core-platform-cppflags += -DTEE_SHMEM_SIZE=0x400000
endif
ifneq ($(PLAT_OPTEE_RESERVED_SIZE),)
core-platform-cppflags += -DTEE_RESERVED_SIZE="$(PLAT_OPTEE_RESERVED_SIZE)"
else
core-platform-cppflags += -DTEE_RESERVED_SIZE=0x2000000
endif
```
TZDRAM_BASE: OPTEE镜像加载地址，也决定linux中给optee reserved-memory的起始地址，以及firewall保护的起始地址；

TEE_RESERVED_SIZE：OP-TEE 运行时需要占用的 DDR 大小，也决定 Linux 中为 OP-TEE reserved-memory 分配的大小。

TEE_SHMEM_SIZE：OPTEE和linux共享的内存大小。

## 3.3 CA/TA编译

参考msp/sample/optee/sample_optee_hello_world下host（CA）和ta（TA）目录的编译，对于TA编译，是会有签名的动作的，默认使用boot/optee/optee_os-3.21.0/keys/default_ta.pem，如果需要修改，则可以直接替换掉default_ta.pem中内容或者通过optee目录makefile中TA_SIGN_KEY指定自己的私钥。

OPTEE还支持把ta编译到optee os中，ta目录位于boot/optee/optee_os-3.21.0/ta下，通过boot/optee/optee_os-3.21.0/core/arch/arm/plat-axera/conf.mk中配置选择ta是否编译：

```
CFG_IN_TREE_EARLY_TAS += efuse/02ce55ec-e616-4270-8806-33a202463585
CFG_IN_TREE_EARLY_TAS += rollback/e5c1d101-25ca-4940-8b78-45743166a36c
#CFG_IN_TREE_EARLY_TAS += pkcs11/fd02c9da-306c-48c7-a49c-bbd827ae86ee
CFG_IN_TREE_EARLY_TAS += secure_debug/99ecfc5d-8c3d-4926-8707-41724464022b
```
## 3.4 OPTEE debug

支持通过串口吐log方式进行debug：

1. opteelog：修改optee/Makefile中的DEBUG_LOG_LEVEL值为0~3，重新编译下载；
2. TA 日志等级设置方式相同，可根据需求修改 ta/Makefile 中的 CFG_TEE_TA_LOG_LEVEL 配置。

## 3.5 OPTEE相关路径说明

/opt/bin/OPTEE：optee sample程序存放路径

/lib/optee_armtz：opteeTA程序存放路径

/data/tee：tee安全存储存放路径

# 4 Secure Debug

## 4.1 M57 Secure Debug概述

M57支持安全调试功能，安全调试用于调试口的安全保护，防止调试口被攻击者非法使用。Debug口支持在产品量产时关闭，关闭后的Debug口芯片不再工作使能。芯片支持两种关闭Debug口方式：

 One-Time Debug：通过烧写eFuse中bond option实现关闭指定的Debug口。

 Authentication Debug：根据软件配置关闭Debug口，可通过认证的方式使能Debug口。

### 4.1.1 One-Time Debug

可通过烧写eFuse的Bond Option相关bit，实现关闭指定Debug口的作用，该操作是一次性行为，烧写后该芯片对应的Debug口无法再使能。

Bond Option0说明：

| **Bit** | **属性** | **状态** | **说明** |
| --- | --- | --- | --- |
| 13 | uart0 | 1:disable | 根据产品需要，决定是否关闭uart0控制器，关闭后不可逆 |
| 12 | emac1 | 1:disable | 根据产品需要，决定是否关闭emac1控制器，关闭后不可逆 |
| 11 | emac0 | 1:disable | 根据产品需要，决定是否关闭emac0控制器，关闭后不可逆 |
| 10 | usb | 1:disable | 根据产品需要，决定是否关闭usb控制器，关闭后不可逆 |
| 7 | jtag | 1:disable | 根据产品需要，决定是否关闭jtag，关闭后不可逆 |

Bond Option1说明：

| **Bit** | **属性** | **状态** | **说明** |
| --- | --- | --- | --- |
| 4 | can6 | 1:disable | 根据产品需要，决定是否关闭can6控制器，关闭后不可逆 |
| 3 | uart1 | 1:disable | 根据产品需要，决定是否关闭uart1控制器，关闭后不可逆 |

### 4.1.2 Authentication Debug

芯片上Safety Sec glb寄存器可以控制Debug口的关闭和使能。Safety Sec glb寄存器有访问权限限制，只允许Secure CPU访问。

| **Reg offset** | **Reg name** | **description** |
| --- | --- | --- |
| 0x468 | usb | default: 0，Write 1 disable usb |
| 0x46c | safety_emac | default: 0，Write 1 disable emac0 |
| 0x470 | main_emac | default: 0，Write 1 disable emac1 |
| 0x474 | safety uart | default: 0，Write 1 disable uart0 |
| 0x478 | uart1 | default: 0，Write 1 disable uart1 |
| 0x47c | can6 | default: 0，Write 1 disable can6 |
| 0x480 | jtag | default: 0，Write 1 disable jtag |

在启动镜像SBL中根据软件的静态配置，实现在启动过程中关闭指定Debug。软件静态配置编译到SBL镜像中，由安全启动保证静态配置无法被篡改。

图4-1 SBL关闭Debug设备

启动过程中关闭了Debug设备，软件上实现认证的方式重新使能Debug口。用户根据自己的需求生成一个Debug控制的配置，配置中会包含哪些Debug口会被使能。配置文件在服务器上通过RSA签名生成带签名的配置。在设备中的TEE中通过公钥对Debug配置的签名进行验签，验签通过后会根据配置中使能对应的Debug。RSA公钥存储在TEE中，由安全启动保证公钥的安全。

图4-2 认证使能Debug设备

Debug控制配置中存有使能Debug口的次数，生成动态配置存储在Flash中。目的是在下次重启时SBL会根据动态配置重新配置Debug的使能。每次启动Debug口使能的有效次数会自动减1。当Debug口使能有效次数为0时，SBL软件不会根据Flash中Debug口的动态配置设置Debug口的状态。Debug口的动态配置参考如下：

JTAG_DEBUG_ENABLE=TRUE

DEBUG_ENABLE_TIMES=10

为了确保Flash中存储的Debug口动态配置不会被非法篡改，Debug口动态配置会调用HSM使用RootKey计算出hmac值一同存储在Flash中。

图4-3 Debug配置HMAC生成

在SBL启动阶段，首先会先把Debug口的静态配置设置好，然后会读取Flash中Debug口的动态配置和对应的HMAC值，调用HSM对Hmac进行Verify，确保动态配置合法。然后判断动态配置中DEBUG_ENABLE_TIMES次数，设置使能Debug配置中的Debug口。设置成功后，会更新Debug动态配置，调用HSM重新生成HMAC，一同写入Flash固定位置。

图4-4 SBL Debug配置文件更新

## 4.2 Secure debug方案实施

### 4.2.1 One-Time Debug配置

烧写eFuse可实现一次性永久性关闭Debug口，烧写对应的eFuse bondoption bit可以实现Debug口永久性关闭。具体烧写eFuse方法，可以参考《AX EFUSE使用说明文档》。

### 4.2.2 Authentication Debug配置

如果一次性eFuse没有关闭Debug口，可通过软件配置的方式关闭Debug口，并且可以通过认证方式重新打开Debug口。Secure debug有个总配置开关，默认配置中Secure debug是不使能的，需要用户根据需求配置。Secure debug的配置在build/platforms下的配置，例如build/platforms/axera/demo_nor_nand/config.mk配置：

```
# SECURE_DEBUG: Support secure debug flag (TRUE/FALSE)
# Set to TRUE to enable secure debug in boot.
SECURE_DEBUG          := FALSE
```
静态配置在编译 SBL 时编入程序。配置为 0 时，启动后默认关闭对应的 Debug 设备。配置路径：SafetyIsland/mcal/board/include/sbl/sbl_demo.h

```
/* Config: Secure Debug **/
#if SUPPORT_SECURE_DEBUG
#define USB_DEBUG_ENABLE             1
#define EMAC0_DEBUG_ENABLE           1
#define EMAC1_DEBUG_ENABLE           1
#define UART0_DEBUG_ENABLE           1
#define UART1_DEBUG_ENABLE           1
#define CAN6_DEBUG_ENABLE            1
#define JTAG_DEBUG_ENABLE            0
#endif
```
动态配置位于msp/sample/secure_debug/debug_config.mk

```
# config debug enable TRUE or FALSE
USB_DEBUG_ENABLE=TRUE
EMAC0_DEBUG_ENABLE=TRUE
EMAC1_DEBUG_ENABLE=TRUE
UART0_DEBUG_ENABLE=TRUE
UART1_DEBUG_ENABLE=TRUE
CAN6_DEBUG_ENABLE=TRUE
JTAG_DEBUG_ENABLE=TRUE
# config debug boot enable times >= 0
DEBUG_ENABLE_TIMES=1
```
用户修改完动态配置后，可以在编译secure_debugsample时完成对配置的签名。签名的RSA私钥默认使用和安全启动相同的密钥。带签名的配置和sample_secure_debug会拷贝到msp/out/bin 目录下。sample_secure_debug可运行在设备中，通过传入带签名的debug配置，调用TEE接口完成验签，在TEE中RSA验签成功会解析配置中的设置，并使能对应的Debug接口设备。生成经过加密后的动态配置文件，并写入指定的Flash分区位置。

### 4.2.3 安全Debug注意事项

1. eFuse可关闭指定的Debug接口，一旦写入，不可逆。
2. 带签名的debug配置，可在需要debug时通过一定方式传入设备系统中，调用sample_secure_debug完成对指定debug接口的释放。此时除 JTAG 外，其他调试接口需在驱动完成初始化后才能恢复工作。
3. Debug口被关闭后，CPU无法访问该debug口，所以在启动过程中可能该debug接口会初始化驱动失败。

# 5 Secure Access

## 5.1 Firewall&Sema

### 5.1.1 Firewall&Sema概述

Firewall模块用于实现Safety域和Main域的访问隔离，以及RAM上Master访问权限控制。Safety域有三个Firewall模块和一个Sema模块，其中FW_0是限制Main域的Master访问Safety资源。FW_1是实现对Safety SRAM的保护，限制Master对Safety SRAM的访问。FW_2是限制Safety域的Master访问Main域资源。Sema模块是用于保护Safety域64KB IRAM。Main域有两个Firewall模块，分别是FW_P01和FW_P234，限制Master对Main域的DDR的访问。

图5-1 Firewall&Sema硬件架构图

Firewall和Sema相比较有较强的硬件特性，Firewall具备功能：

1. 支持region配置，设置region的起始地址，结束地址，地址需要4KB对齐。设置region可访问的master。
2. 每个Firewall支持多个region配置，region之间可地址重叠。
3. Master访问权限可控，可实现只读和可读写控制，可实现master Non-secure访问。

Sema具备的功能：

1. 64KB IRAM独立划分16个4KB大小region，每个region可独立配置Secure访问属性。
2. Sema不区分master和读写访问，只能限制Non-secure访问。

不同的Firewall可配置的region数量和master不同：

| Firewall | Region最大数量 | Master数量 | 可配master |
| --- | --- | --- | --- |
| FW_0 | 10 | 4 | Main域的master:<br>CPU<br>EMMC<br>DMA_PER<br>RGMII |
| FW_1 | 4 | 14 | Safety Island的master:<br>R5F0<br>R5F1<br>CE(HSM)<br>DMA_PER<br>AXDMA<br>CRC_ENGINE<br>GZIP<br>RGMII<br>SPI2AXI<br>DAP<br>Main域的master:<br>CPU<br>EMMC<br>DMA_PER<br>RGMII |
| FW_2 | 8 | 8 | Safety Island的master:<br>R5F0<br>R5F1<br>CE(HSM)<br>DMA_PER<br>AXDMA<br>CRC_ENGINE<br>GZIP<br>RGMII |
| FW_P01 | 8 | 12 | Main域的master:<br>CPU<br>NPU<br>Safety Island的master:<br>R5F0<br>R5F1<br>CE(HSM)<br>DMA_PER<br>AXDMA<br>CRC_ENGINE<br>GZIP<br>RGMII<br>SPI2AXI<br>DAP |
| FW_P234 | 8 | 11 | Main域的master:<br>ISP<br>MM<br>VENC<br>EMMC<br>SDIO<br>DMA_PER<br>USB<br>CRC_ENGINE<br>DMA_PER<br>AXDMA<br>RGMII |

Firewall的操作流程：

图5-2 Firewall操作流程图

Sema用于保护Safety域64KB IRAM区域，IRAM被分为16个4KB大小的区域，每个区域可独立控制访问权限。可以控制该区域允许所有Master访问或只允许Secure Master访问。

### 5.1.2 Firewall&Sema配置

Safety Island的Firewall和Sema的配置参考SDK目录的SafetyIsland/mcal/mcal_drv/FW/Doc/《AXERA-M57 CDD Firewall UM.docx》文档。

Main域DDR的Firewall的配置分为静态配置和动态配置两部分。目前静态配置在atf代码仓库的firewall驱动中静态配置。参考: boot/atf/arm-trusted-firmware-2.8.0/plat/axera/m57/drivers/firewall/firewall.c。

目前静态配置最多可以配置4个DDR保护region，目前已经配置了两个region，分别是ATF运行的DDR区域和OPTEE运行的DDR区域。参考fw_region数组

```
static const fw_region_t fw_region[] = {
        {
.region_start_4KB = ATF_IMG_ADDR >> 12,
.region_end_4KB = (ATF_IMG_ADDR + ATF_IMG_PKG_SIZE - 1) >> 12,
.region_permitted_master = (1u << MASTER_ID_CPU_CA55) | (1u << MASTER_ID_SAFETY_CE),  /* only cpu&ce are permitted */
.region_master_write_control = (1u << MASTER_ID_CPU_CA55) | (1u << MASTER_ID_SAFETY_CE),  /* cpu&ce can write & read */
.region_ignore_master_prot = 0,
         },
#ifdef OPTEE_BOOT
        {
.region_start_4KB = OPTEE_IMAGE_ADDR >> 12,
.region_end_4KB = (OPTEE_IMAGE_ADDR + OPTEE_RESERVED_SIZE - OPTEE_SHMEM_SIZE - 1) >> 12,
.region_permitted_master = (1u << MASTER_ID_CPU_CA55) | (1u << MASTER_ID_SAFETY_CE),  /* only cpu&ce are permitted */
.region_master_write_control = (1u << MASTER_ID_CPU_CA55) | (1u << MASTER_ID_SAFETY_CE),  /* cpu&ce can write & read */
.region_ignore_master_prot = 0,
         },
#endif
};
```
其中fw_region各个参数的意义如下：

| **Parameter** | **Description** |
| --- | --- |
| region_start_4KB | 保护区域的起始的 4 KB 区域 |
| region_end_4KB | 保护区域的结束的 4 KB 区域 |
| region_permitted_master | 允许访问的Master，可配置多个 |
| region_master_write_control | 配置各 Master 对保护区域的写权限 |
| region_ignore_master_prot | 配置是否忽略各个Master的secure属性，配置为1时，则Non-secure Master也可以访问 |

Firewall的动态配置是在optee中完成，可以通过参考msp/sample/optee/optee_firewall代码动态配置保护region。动态region也最多配置4个region，序号为0~3。支持设置和删除两个接口动态配置firewall的保护region。

```
/*
 * in   params[0].value.a  input region idx
 *      params[1].memref  input region set info
 */
#define TA_FIREWALL_CMD_SET_REGION              0
/*
 * in   params[0].value.a  input region idx
 */
#define TA_FIREWALL_CMD_DEL_REGION              1
```
> 注意：

> 为了确保Firewall的配置只能在secure下配置，参考《AX EFUSE使用说明.docx》中把bondoption中sec位烧写使能。

## 5.2 安全外设

### 5.2.1 安全外设概述

Main 域的各个外设可独立配置访问权限，可配置为仅允许 Secure Master 访问，或允许 Secure/Non-secure Master 访问。Main 域的 Master 中，支持 TrustZone 的 CPU 既可以是 Secure Master，也可以是 Non-secure Master；其他 Master 可静态配置 Secure 属性。Secure Master 可访问 Secure/Non-secure Slave，Non-secure Master 只能访问 Non-secure Slave。只能在 TEE 中访问的外设应配置为 Secure Slave，例如 Firewall。

### 5.2.2 安全外设配置

安全外设支持静态配置，参考boot/atf/arm-trusted-firmware-2.8.0/plat/axera/m57/drivers/secure_mst_slv中secure_slv.c源码中secure_slv配置，已经列出了各个slave的配置状态，SEC_DISABLE 表示配置为 Non-secure slave，SEC_ENABLE 表示配置为 Secure slave。

> 注意：

> GPIO控制器32bit可独立配置各个GPIO的secure属性。

安全Master也是支持静态配置，参考secure_mst.c源码secure_mst可独立配置各个master发出的读写Secure属性。

> 注意：

> 为了确保安全外设的配置只能在secure下配置，参考《AX EFUSE使用说明.docx》中把bondoption中sec位烧写使能。

## 5.3 安全登录

### 5.3.1 uboot串口登录

SDK中的uboot打开了串口功能，开发人员可以在uboot启动阶段通过按任意键方式中断uboot的执行过程，进入uboot的命令行，执行调试功能。产品正式发布，用户可采用以下措施关闭uboot从串口进入命令行功能。

修改uboot的配置CONFIG_BOOTDELAY设置为-2，则禁止uboot串口登录功能。

```
CONFIG_BOOTDELAY=-2
```
### 5.3.2 linux串口登录

SDK进入linux下串口默认不需要登录可直接进入shell命令行，用于开发人员调试使用。用户可设置登录，通过输入正确的用户名和密码进入shell命令行。

**设置root账户密码**

步骤1 在设备rootfs中的/etc/inittab文件中，内容如下：

添加“console::respawn:/sbin/getty -L  console 0 vt100”设置登录界面。并注释原有的“::respawn:-/bin/sh”

```
# Put a getty on the serial port
console::respawn:/sbin/getty -L  console 0 vt100 # GENERIC_SERIAL
# ::respawn:-/bin/sh
```
步骤2 设置root登录密码

可以在设备shell中通过passwd命令设置password，推荐使用sha512算法对密码进行保存。

```
root@m57:~ # passwd -a sha512 root
Changing password for root
New password:
Retype password:
passwd: password for root changed by root
```
也可以通过在linux编译服务器上通过openssl工具生成password，预写入到rootfs的/etc/shadow文件中。

```
$ openssl passwd -6 "my_secure_password123"
$6$PuiqM66hoGllfz5n$Zgu3/JbvEUIgdewVOgD7BjuD2a7z7rcS8st6nbyFSdZTvYJLiXjfzCwyz15kjRDzx9r0J9zr/pFiSevR0VvU7.
```
写入到/etc/shadow的root:后区域

```
root:$6$PuiqM66hoGllfz5n$Zgu3/JbvEUIgdewVOgD7BjuD2a7z7rcS8st6nbyFSdZTvYJLiXjfzCwyz15kjRDzx9r0J9zr/pFiSevR0VvU7.:1::::::
```
**设置PAM配置**

SDK默认配置，当用户登录时，如果输入密码连续错误3次，会锁定5分钟，5分钟释放后可重新登录。可以修改rootfs中/etc/security/faillock.conf配置文件修改登录失败锁定的配置。

| **parameter** | **description** |
| --- | --- |
| deny | 连续登录失败最大次数，达到次数后会锁住登录 |
| unlock_time | 锁定 n 秒后重新启用访问权限。 |

### 5.3.3 SSH服务

SDK默认开启了SSH服务，默认端口号22。用户名及密码是和串口登录相同。SSH登录保护也支持连续登录锁住功能，和串口登录使用相同的配置。在产品量产阶段，建议关闭SSH服务，删除rootfs中sshd进程启动脚本。

```
# rm /etc/init.d/S50sshd
```
### 5.3.4 Telnet服务

SDK默认开启了telnet服务，默认端口号23。用户名及密码是和串口登录相同。telnet登录保护也支持连续登录锁住功能，和串口登录使用相同的配置。在产品量产阶段，建议关闭telnet服务，删除rootfs中telnet进程启动脚本。

```
# rm /etc/init.d/S50telnet
```
## 5.4 SELinux

### 5.4.1 SELinux概述

安全增强型Linux（SELinux）是一种采用安全架构的 Linux系统，它能够让管理员更好地管控哪些人可以访问系统。它最初是作为 Linux 内核的一系列补丁，由美国国家安全局（NSA）利用 Linux 安全模块（LSM）开发而成。SELinux主要作用是最大限度地减少系统中服务进程可访问的资源（最小权限原则）。

SELinux 的核心概念是将进程与资源分别标记为主体（subject）和客体（object），当一个进程需要访问或操作一个文件或某个资源（如网络端口、文件描述符、管道等），系统需要明确规则（rule）允许该进程执行这些操作，系统将所有的规则都集中放入策略文件（policy），传递给内核运行这些规则。

系统将资源进行分类处理，如文件、进程，被称为类别（class），每个类别都包含各自的操作权限（permission）。

图5-3 SELinux权限管理

SELinux另一个关键的概念是安全上下文（Security Context）也被称为安全标签（Security Label），可分进程（主体）安全上下文与文件（客体）安全上下文。其格式如下：

user:role:type

 user SELinux 用户身份是策略已知的身份，它授权用于一组特定的角色，以及特定的 MLS/MCS 范围。

 role SELinux 的一部分是基于角色的访问控制(RBAC)安全模型。该角色是 RBAC 的一个属性。SELinux 用户获得角色的授权，并且域对角色进行了授权。该角色充当域和 SELinux 用户之间的中介。

type type是 Type Enforcement 的属性。类型定义进程的域，以及文件的类型。

SELinux 策略规则定义类型如何互相访问，无论是访问某一类型的域还是访问其他域的域。只有在存在允许访问的特定 SELinux 策略规则时才允许访问。

### 5.4.2 SELinux配置

默认配置中 SELinux 未启用，用户可根据需求配置，配置文件位于 build/platforms/axera/demo_nor_nand/config.mk：

```
# Enable or disable Selinux support (TRUE/FALSE)
ENABLE_SELINUX        := FALSE
```
如果启用 SELinux，由于 SELinux 与默认 BusyBox 配置不兼容，需要重新构建 rootfs。进入 rootfs 目录执行以下命令重新编译 Buildroot，首次编译耗时较长。

```
make PLAT=demo_nor_nand rootfs
```
编译生成新的rootfs/prebuilt/rootfs.cpio.lz4压缩文件，后续如果不更新buildroot配置，则无需编译buildroot。使能SELinux后，rootfs编译出的镜像会比原镜像多占用11MB大小。SELinux的buildroot配置位于rootfs/buildroot-2024.02.2/configs/m57_selinux.config下，默认配置可以满足selinux的调试，

```
BR2_PACKAGE_POLICYCOREUTILS=y
BR2_PACKAGE_REFPOLICY=y
BR2_PACKAGE_RESTORECOND=y
```
如果想极致裁剪buildroot，只保留selinux最基本的功能，那么m57_selinux.config配置只保留如下：

```
BR2_PACKAGE_REFPOLICY=y
```
rootfs编译出的镜像会比原镜像多占用约3MB大小。
如果想再多一些selinux调试手段和工具，则m57_selinux.config配置放开setools，如下：

```
BR2_PACKAGE_PYTHON3=y
BR2_PACKAGE_POLICYCOREUTILS=y
BR2_PACKAGE_REFPOLICY=y
BR2_PACKAGE_RESTORECOND=y
BR2_PACKAGE_CHECKPOLICY=y
BR2_PACKAGE_SETOOLS=y
```
那么rootfs编译出的镜像会比原镜像多占用约50MB大小。

### 5.4.3 SELinux调试

 **SELinux状态查询**

使能SELinux后进入linux下，默认模式是“permissive”，即selinux会记录权限不匹配的信息，但不会拦截，通过sestatus工具查看：

```
root@m57:~ # sestatus
SELinux status:                 enabled
SELinuxfs mount:                /sys/fs/selinux
SELinux root directory:         /etc/selinux
Loaded policy name:             targeted
Current mode:                   permissive
Mode from config file:          permissive
Policy MLS status:              disabled
Policy deny_unknown status:     denied
Memory protection checking:     actual (secure)
Max kernel policy version:      33
```
SELinux status: enabled 表示SELinux已启用

Current mode: enforcing 表示强制模式，未经允许禁止访问

 **SELinux模式修改**

如果想要使selinux强制拦截，需要把模式改成“enforcing”。

在宽容模式与强制模式之间临时切换的命令：setenforce

```
root@m57:~ # setenforce 1
root@m57:~ # sestatus
SELinux status:                 enabled
SELinuxfs mount:                /sys/fs/selinux
SELinux root directory:         /etc/selinux
Loaded policy name:             targeted
Current mode:                   enforcing
Mode from config file:          permissive
Policy MLS status:              disabled
Policy deny_unknown status:     denied
Memory protection checking:     actual (secure)
Max kernel policy version:      33
```
setenforce 0 表示临时关闭SELinux拦截，Current mode变成permissive（宽容模式）。

setenforce 1 表示开启SELinux拦截。

可以修改/etc/selinux/config配置文件，让selinux模式长期生效：

```
# This file controls the state of SELinux on the system.
# SELINUX= can take one of these three values:
#     enforcing - SELinux security policy is enforced.
#     permissive - SELinux prints warnings instead of enforcing.
#     disabled - No SELinux policy is loaded.
SELINUX=permissive
```
 **安全上下文查看**

ls -Z 选项可以查看SELinux的文件安全上下文信息。

```
root@m57:/opt # ls -Z
      system_u:object_r:bin_t bin  system_u:object_r:unlabeled_t data        system_u:object_r:usr_t etc        system_u:object_r:usr_t ko        system_u:object_r:lib_t lib        system_u:object_r:usr_t msp
```
与ls命令一样，ps -Z 与 id -Z 命令查看进程的安全上下文。

```
root@m57:/opt # ps -aux -Z
LABEL                           USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
system_u:system_r:init_t        root         1  0.0  0.2   4300   776 ?        Ss   12:52   0:01 init
system_u:system_r:kernel_t      root         2  0.0  0.0      0     0 ?        S    12:52   0:00 [kthreadd]
system_u:system_r:kernel_t      root         3  0.0  0.0      0     0 ?        I<   12:52   0:00 [rcu_gp]
system_u:system_r:kernel_t      root         4  0.0  0.0      0     0 ?        I<   12:52   0:00 [rcu_par_gp]
system_u:system_r:kernel_t      root         5  0.0  0.0      0     0 ?        I<   12:52   0:00 [slub_flushwq]
```
 **更改安全上下文**

- chcon可以修改安全上下文的user/role/type字段，需要注意的是修改的字段需要是声明过的有效值，否则修改失败。
- restorecon可以将修改后的文件恢复默认的安全上下文。

```
root@m57:~ # touch test
root@m57:~ # ls -Z test
root:object_r:user_home_t test
root@m57:~ # chcon -u system_u -r object_r -t bin_t test
root@m57:~ # ls -Z test
system_u:object_r:bin_t test
root@m57:~ # restorecon test
root@m57:~ # ls -Z test
system_u:object_r:user_home_t test
```
SELinux的上下文默认配置是在/etc/selinux/targeted/contexts/files/file_contexts文件中，restorecon命令恢复的即是默认配置中设置的安全上下文属性。

默认使能了restorecond后台进程，用于监控安全上下文被修改，能够及时恢复。restorecond会根据/etc/selinux/restorecond.conf配置监控对应目的安全上下文，用户可以根据需求修改。

```
root@m57:~ # cat /etc/selinux/restorecond.conf
/etc/services
/etc/resolv.conf
/etc/samba/secrets.tdb
/etc/updatedb.conf
/run/utmp
/var/log/wtmp
/root/*
/root/.ssh/*
```
 **Selinux日志查询**

使能Selinux后默认使能了audit功能，可以通过查看audit日志查Selinux的日志。

audit 日志路径是 /var/log/audit/audit.log。如果
从日志中可以看到“type=AVC”打头的日志信息，则是拒绝信息，例如：

```
type=AVC msg=audit(5.548:8): avc:  denied  { open } for  pid=791 comm="syslogd" path="/opt/data/AXSyslog/kernel/user.log" dev="ubifs" ino=87 scontext=system_u:system_r:syslogd_t tcontext=system_u:object_r:unlabeled_t tclass=file permissive=1
```
| **parameter** | **description** |
| --- | --- |
| type=AVC | 表示这是一条由 SELinux 的访问向量缓存（AVC）生成的审计消息 |
| msg=audit | 审计消息的时间戳。格式通常是秒.微秒:序列号 |
| avc: denied | SELinux拒绝的原因 |
| pid | 进程的 ID |
| comm | 进程名称 |
| path | 目标文件的完整路径 |
| dev | 文件所在的设备使用的文件系统 |
| ino | 文件的 inode 号 |
| scontext | **发起操作的进程**的 SELinux 安全上下文 |
| tcontext | **被访问的对象**的 SELinux 安全上下文 |
| tclass | 被访问对象的类别 |
| permissive | =1表示发生此操作时正处于**“宽容模式（Permissive Mode）”** |

 **更新SElinux策略**

目前 SELinux 可由 Buildroot 中的 refpolicy 代码静态编译策略文件。策略文件路径为：/etc/selinux/targeted/policy/policy.31

进入buildroot的下载目录：rootfs/buildroot-2024.02.2/dl/refpolicy，制作refpolicy patch。

```
$ tar xjf refpolicy-2.20231002.tar.bz2
$ cp -rf refpolicya
$ cp -rf refpolicy b
```
在 refpolicy 代码目录的 policy/modules 中创建自己的 *.te、*.if、*.fc 文件，或直接修改 refpolicy 自带的策略。修改后生成一个patch到rootfs/buildroot-2024.02.2/package/refpolicy/2.20231002目录下

```
$ diff -Naur a b > ../../package/refpolicy/2.20231002/0003-policy-modeles-new.patch
```
buildroot 重新执行 refpolicy-rebuild，生成新的rootfs即可以更新策略。

# 6 Secure Storage

## 6.1 TEE安全存储

### 6.1.1 TEE安全存储概述

基于OP-TEE的安全存储是TEE内部的核心功能，TEE安全存储实现对数据的加密存储，可以实现数据存储的完整性和修改存储操作的原子性。TEE安全存储可以存储通用数据也可用来存储密钥。基于OP-TEE的安全存储有两种实现：

1. 一种是常规的REE FS方案，不依赖存储介质，可以是Flash或者eMMC。
2. 另一种是基于eMMC的RPMB分区实现的RPMB FS。

#### REEFS

要存储的数据在Linux端调用TA接口传递给TEE，TA调用到optee os中，在optee os中生成密钥，完成对数据的加密，回调到Kernel的TEE驱动，请求tee-supplicant工具完成对数据的写入。REE FS存储的目录是linux所在的文件系统/data/tee目录，所以要求/data/tee目录可读写。

图6-1 TEE FS安全存储架构

TEE FS安全存储最关键的是如何管理密钥，在optee os中安全存储涉及3个密钥，Secure Storage Key (*SSK*),Trusted Application Storage Key (*TSK*)和File Encryption Key (*FEK*)。

SSK是由optee os启动时通过TEE HUK派生生成的，SSK可用来派生TSK。SSK的派生过程：

```
SSK = HMAC (TEE HUK, Chip ID || “static string”)
```
TSK是每个TA独立的一个密钥，可以用来对FEK加密，TSK的派生过程：

```
TSK = HMAC (SSK, TA_UUID)
```
FEK是安全存储中实际给数据加密的密钥，每次加密会通过随机数生成一个新的FEK，FEK对元数据的加密过程及FEK的保存流程如下：

1. 通过随机数生成一个新的FEK。
2. FEK对元数据AES-GCM 加密生成密文数据和Tag，加密的IV也是通过随机数生成。
3. TSK对明文的FEK加密后，密文FEK和密文数据合并在一起传递给REE端写入到文件系统中。

图6-2 TEE安全存储元数据加密过程

图6-3 TEE安全存储元数据解密过程

#### RPMBFS

RPMB（Replay Protected Memory Block重放保护内存块）Partition 是 eMMC 中的一个具有安全特性的分区。eMMC 在写入数据到 RPMB 时，会校验数据的合法性，只有指定的 Host 才能够写入，同时在读数据时，也提供了签名机制，保证 Host 读取到的数据是 RPMB 内部数据，而不是攻击者伪造的数据。

RPMB 在实际应用中，通常用于存储一些有防止非法篡改需求的数据。 RPMB 可以对写入操作进行鉴权，但是读取并不需要鉴权，任何人都可以进行读取操作，因此存储到 RPMB 的数据通常会进行加密后再存储。使用RPMB FS方案安全存储，也是会对元数据加密，加密过程和TEE FS类似。

RPMB 数据读取的流程如下：

图6-4 RPMB数据读取过程

1. Host 向 eMMC 发起读 RPMB 的请求，同时生成一个 16 bytes 的随机数，发送给 eMMC。
2. eMMC 将请求的数据从 RPMB 中读出，并使用 Secure Key 通过 HMAC（哈希消息验证码） SHA-256 算法，计算读取到的数据和接收到的随机数拼接到一起后的签名。然后，eMMC 将读取到的数据、接收到的随机数、计算得到的签名一并发送给 Host。
3. Host 接收到 RPMB 的数据、随机数以及签名后，首先比较随机数是否与自己发送的一致，如果一致，再用同样的 Secure Key 通过 HMAC SHA-256 算法对数据和随机数组合到一起进行签名，如果签名与 eMMC 发送的签名是一致的，那么就可以确定该数据是从 RPMB 中读取到的正确数据，而不是攻击者伪造的数据。

RPMB 数据写入的流程如下：

图6-5 RPMB数据写入过程

1. Host 按照上面的读数据流程，读取 RPMB 的 Write Counter。
2. Host 将需要写入的数据和 Write Counter 拼接到一起并计算签名，然后将数据、Write Counter 以及签名一并发给 eMMC。eMMC 接收到数据后，先对比 Write Counter 是否与当前的值相同，如果相同那么再对数据和 Write Counter 的组合进行签名，然后和 Host 发送过来的签名进行比较，如果签名相同则鉴权通过，将数据写入到 RPMB 中。

RPMB 的 Secure Key 由 OP-TEE OS 派生生成，当第一次访问RPMB时，会写入Secure Key。RPMB Secure Key的派生过程是：

```
RPMB Key = HMAC (TEE HUK, eMMC CID)
```
RPMB FS时，对数据的加密/解密过程都在optee os中完成，tee-supplicant 工具只负责把经过RPMB Key签名的数据写入到RPMB分区。如果使能 RPMB FS，则不会生成 /data/tee 目录。

### 6.1.2 TEE安全存储实施

SDK默认已经支持了REE FS安全存储，如果是eMMC设备，需要使能RPMB FS则需要在optee的Makefile中适配支持。例如demo_nor_emmc设备使能RPMB FS功能。

```
ifeq ($(PLATFORM),demo_nor_emmc)
OPTEE_PLAT := m57_emmc
endif
```
SDK提供了tee secure storage的sample供参考，路径：msp/sample/optee/optee_sec_storage，用户可以根据自己的需求设计ta和ca。

在TA中调用 GlobalPlatform TEE Internal Core API 规范中定义接口实现数据的安全存储，TEE安全存储将数据组织为 "对象" (Objects)，而不是简单的字节流。每个对象都有元数据（属性）和实际的数据负载。

| **Interface** | **Description** |
| --- | --- |
| TEE_CreatePersistentObject | 创建（可覆盖）一个持久化对象 |
| TEE_OpenPersistentObject | 打开一个已存在的对象 |
| TEE_ReadObjectData | 从对象读取数据 |
| TEE_WriteObjectData | 向对象写入数据 |
| TEE_CloseObject | 关闭对象句柄，释放资源 |
| TEE_CloseAndDeletePersistentObject | 关闭并立即删除对象 |

## 6.2 HSM安全存储

### 6.2.1 HSM安全存储概述

TEE安全存储受限在Main域使用，HSM 安全存储可以在 Safety 域和 Main 域使用。HSM安全存储可以存储密钥，经过加密后的密钥可以临时存储在内存中，或者持久性的存储在Flash/eMMC或者eFuse中。

HSM的Key的存储是基于HSM唯一的根密钥管理，可以通过HSM的TRNG生成Key或者导入明文的Key。通过HSM安全加密的Key，可以存储在存储介质Flash中。HSM存储的Key可以限定Key的使用算法和生命周期。

图6-6 HSM Key安全存储加密过程

通过HSM加密的Key Blob存储在Flash中，当设备重启时，可以从Flash中读出，并导入到HSM中获取 Key ID，通过Key ID达到对Key的使用。

图6-7 HSM Key安全存储解密过程

### 6.2.2 HSM安全存储实施

#### Main域HSM安全存储

在Main域调用HSM的API接口可以实现Key Blob生成和导入的过程。参考代码路径：msp/sample/hsm。

| **interface** | **description** |
| --- | --- |
| AX_HSM_KeyBlobGenrate | 创建生成密文密钥的Key Blob |
| AX_HSM_KeyBlobImport | 导入一个加密的Key Blob，获取Key ID |
| AX_HSM_KeyBlobDelete | 根据Key ID，删除HSM中的密钥 |

## 6.3 AI 模型保护

### 6.3.1 AI模型保护概述

AI模型作为公司的核心数据资产，不能轻易被攻击者读取和滥用。那么AI 模型需要以密文形式保存在设备中，并且只有经过授权的设备才能够拿到密钥解密模型并运行。为了满足量产要求，密文的模型文件和给模型解密的密钥(PEK)是独立存储的。在产品生产阶段或者OTA阶段设备可以获取可信的芯片UID，请求授权服务器通过TLS获取解密的PEK。PEK在设备中经过HSM的安全加密存储在存储介质中。

图6-8 AI模型授权安全存储PEK过程

在设备中密文的AI模型文件传入HSM，HSM通过PEK Key Blob解密后获取明文的PEK，通过 PEK 解密密文 AI 模型，解密后的 AI 模型数据交给 NPU 执行。

图6-9 AI模型密文解密过程

### 6.3.2 AI模型保护实施

密文AI模型执行参考《AX ENGINE API 使用说明》文档中接口

| **interface** | **description** |
| --- | --- |
| AX_ENGINE_GetEncModelType | 通过读取密文模型内存buffer获取模型类型 |
| AX_ENGINE_CreateHandleV2 | 支持密文模型创建 |

## 6.4 FDE

### 6.4.1 FDE概述

FDE(Full-Disk Encryption)是基于文件系统block实现的对整个分区加密的。在Linux下使用dm-crypt实现全盘加密功能，在mapper device上挂载文件系统。在文件系统的读写，kernel底层自动实现对文件的解密和加密操作，存储在块设备上的数据是密文。

图6-10 dm-crypt读写过程

### 6.4.2 FDE实施

**创建全盘加密分区**

在设备中进入linux下，选择一个空的分区，作为全盘加密使用。

1. 生成FDE密钥，比如可以通过随机数生成

```
dd if=/dev/urandom of=/etc/luks_key.bin bs=1 count=32
```
2. 使用cryptsetup工具把分区格式化luks

```
cryptsetup luksFormat /dev/mmcblk0p12 --key-file /etc/luks_key.bin --batch-mode --force-password
```
3. 创建mapper设备

```
cryptsetup open /dev/mmcblk0p12 crypt_mmc --key-file /etc/luks_key.bin
```
4. 对分区进行格式化对应的文件系统

```
mke2fs /dev/mapper/crypt_mmc
```
**挂载全盘加密分区**

创建全盘加密分区后，需要先创建 mapper 设备，再挂载分区

1. 创建mapper设备，传入正确的luks密码

```
cryptsetup open /dev/mmcblk0p12 crypt_mmc --key-file /etc/luks_key.bin
```
2. 挂载加密分区

```
mount /dev/mapper/crypt_mmc /mnt/crypted
```
这样在挂载目录下读写文件，即会加密存储在对应的块设备分区上。

> 注意：

> 因为ubifs文件系统是挂载在ubi卷上的，而非块设备上。mapper设备的原理是基于块设备上实现，所以ubifs不支持FDE功能。

## 6.5 日志安全

### 6.5.1 日志安全概述

AX SYSLOG系统存储的日志包括启动，OTA，及运行相关日志。如果日志不加密存储，则会明文存储在介质中。为了防止日志被篡改，需要对存储的日志文件加密处理。日志加密所使用的方案是Linux自带的eCryptfs方案。fscrypt特性也包括内核态和用户态两部分，内核态部分是实现在fs/crypto目录的公用加解密模块，支持ext4、UBIFS文件系统集成使用。eCryptfs是挂载在已有的文件系统中，所以使用更灵活。

应用程序发起系统调用时先经过VFS，判断目录类型为eCryptfs时调用eCryptfs模块的注册函数。之后eCryptfs根据mount session中保存的key signature参数从keyring中找到对应密钥（FEKEK），再调用crypto模块API完成文件加解密。

图6-11 eCryptfs架构图

eCryptfs核心加解密机制如下图，主要特点归纳如下：

1. FEK（File Encryption Key）唯一，即每个文件的加密密钥均不同，是随文件创建时生成的一个随机数。
2. 每个文件的FEK经过FEKEK（File Encryption Key Encryption Key）加密保护，加密后FEK称为EFEK（Encrypted File Encryption Key），并保存在eCryptfs加密文件的header信息中。
3. passphrase模式下，FEKEK是基于用户passphrase_passwd派生而来，派生方式是hash计算。
4. 文件内容按照page大小（Data Extent）进行块加密。

让AX SYSLOG输出日志的目录挂载eCryptfs，实现对日志的加密。其中比较关键的一点是eCryptfs的passphrase_passwd 的来源及保护方式，确保其不会泄露。此方案中passphrase_passwd是通过HSM派生而来。

图6-12 日志eCryptfs的passphrase_passwd生成过程

### 6.5.2 日志安全实施

默认配置中 eCryptfs 未启用，用户可根据需求配置，配置文件位于 build/platforms/axera/demo_nor_nand/config.mk：

```
# Enable or disable Ecryptfs support (TRUE/FALSE)
# Set to TRUE to enable AXsyslog cipher.
SUPPORT_ECRYPTFS      := FALSE
```
# 7 Secure Update

## 7.1 OTA安全

### 7.1.1 OTA安全概述

在OTA打包时，将各个软件镜像的SHA256值写入sw-description，对sw-description进行RSA签名。

OTA 过程如下：

1. OTA时先下载sw-description和sw-descriptionsignature，并从当前系统中获取RSA公钥，然后对sw-descriptionsignature进行RSA验签。
2. sw-description中会记录需要更新各个镜像的SHA256和当前OTA打包软件版本，首先会对OTA打包软件版本和当前软件版本进行anti-rollback检查。
3. 通过后会下载需要升级的镜像，并对下载的镜像SHA256计算，并和sw-description文件中的SHA256值对比，对比相同时再将镜像写入对应的分区。

图7-1 OTA安全校验过程

### 7.1.2 OTA安全实施

参考《AX SDK使用说明.docx》中OTA升级使用说明章节。

## 7.2 安全下载

### 7.2.1 安全下载概述

下载是指通过 AXDL 工具为设备更新程序的方式。SoC 芯片支持 USB、SD、UART 和 CAN 四种下载接口，并为下载过程提供安全防护。

1. 可以烧写eFuse关闭指定的下载接口。
2. 使能安全启动后，只有正确签名的下载程序(FDL)才能被运行。

图7-2 FDL被验签过程

### 7.2.2 安全下载实施

在量产阶段，可以根据需求烧写eFuse关闭对应的下载接口。在eFuse的blk64，bond option1区域。烧写eFuse帮助信息可以参考《AX EFUSE使用说明》。

| **Bit** | **属性** | **状态** | **说明** |
| --- | --- | --- | --- |
| 9 | download usb | 1:disable | 根据产品需要，决定是否关闭usb download功能 |
| 8 | download sd | 1:disable | 根据产品需要，决定是否关闭sd download功能 |
| 7 | download uart | 1:disable | 根据产品需要，决定是否关闭uart download功能 |
| 6 | download can | 1:disable | 根据产品需要，决定是否关闭can download功能 |

当eFuse使能安全启动后，使用AXDL工具下载时，会进行对FDL的签名校验，无需额外配置。

## 7.3 Anti Rollback

### 7.3.1 Anti Rollback概述

防回滚(Anti Rollback)是指不允许一个比当前运行版本更低的版本在设备中更新成功。防回滚机制需要在启动和OTA过程中进行配合，不能回退版本更新。

在启动过程中每个软件运行固件都有自己的版本，软件当前版本是通过代码静态编译生成，可以在当前运行的程序中获取。在设备中也要存储各个软件固件的版本，用来启动时和当前版本校验。设备中存有两个Anti Rollback版本，分别是：

   基础版本：产品量产时，版本信息烧写在eFuse中，一次烧写，不可篡改，描述的是一个最基础的出厂版本，当软件中使能Anti Rollback配置后，基础版本是一个最低的版本要求。

   升级版本：存储在Flash/eMMC存储介质中，版本信息可以更新，需要加密/防篡改校验。当下载或者OTA时，更新的版本有变化时，会触发升级版本的变化。

基础版本在eFuse中存储格式参考《AX EFUSE使用说明.docx》

首次启动通过下载或 OTA 更新的防回滚版本时，各个启动镜像会从eFuse中获取基础版本和当前版本进行比较。如果当前版本比获取的基础版本还要低，那拒绝当前版本启动。启动成功后会汇总所有启动镜像的版本进行安全加密后存储到指定分区中。

图7-3 第一次防回滚版本启动过程

当防回滚版本已经在芯片上第一次启动成功后，各个启动镜像的升级版本已经安全存储到指定分区中，并且会烧写一个eFuse的anti-rollback bond option状态。这样确保后续的启动都会获取升级版本，并且镜像会用当前版本和升级版本进行比较。即使升级版本存储区域被破坏，会导致升级版本获取失败，也认为当前镜像启动失败。启动成功后同样会汇总所有启动镜像的版本进行安全加密后存储到指定分区中。

图7-4 防回滚版本后续启动过程

如何确保存储的升级版本中数据不被篡改，需要对升级版本进行加密存储。对软件的升级版本加密的密钥是通过eFuse中RTK派生而来，为了确保版本信息不被篡改，增加了HMAC。密钥管理和对版本的加密/解密操作均在HSM中完成。密文的升级版本和摘要会存储在分区的指定地址。

图7-5 防回滚版本加密过程

### 7.3.2 Anti Rollback实施

默认配置中防回滚功能未启用，用户可根据需求配置，配置文件位于 build/platforms/axera/demo_nor_nand/config.mk：

```
# ENABLE_ANTIROLLBACK: Enable anti-rollback feature (TRUE/FALSE)
# Set to TRUE to enable anti-rollback feature.
ENABLE_ANTIROLLBACK   := FALSE
```
当ENABLE_ANTIROLLBACK使能后，在启动过程中会校验各个镜像的版本。

当前启动镜像版本管理，每个镜像有单独的version.mk配置文件用于记录当前镜像版本。各个镜像版本配置文件，路径位于：

| **启动镜像** | **版本配置文件路径** |
| --- | --- |
| sbl | SafetyIsland/sbl/build/sbl/version.mk |
| rtos | SafetyIsland/mcal/mcal_example/examples/Demo/version.mk |
| spl | boot/uboot/version.mk |
| atf | boot/atf/version.mk |
| optee | boot/optee/version.mk |
| uboot | boot/uboot/version.mk |
| kernel | kernel/linux/version.mk |
| rootfs | rootfs/version.mk |

SDK默认各个镜像的版本与SDK版本中一致，用户可根据自己的需求修改配置自定义各个镜像版本。version.mk内容如下：

```
# USE_SDK_VERSION: Flag to indicate whether use SDK version for software version
# Possible values: TRUE: use the SDK version
# Possible values: FALSE: use the customized version
USE_SDK_VERSION := TRUE
ifeq ($(USE_SDK_VERSION), TRUE)
PRODUCT_SW_VERSION := $(shell $(BUILD_PATH)/scripts/parse_sdk_version.sh "$(SDK_VERSION)")
else
SW_VERSION_MAJOR=0
SW_VERSION_MINOR=1
SW_VERSION_PATCH=0
SW_VERSION_P=0
PRODUCT_SW_VERSION=$(shell echo $$(( $(SW_VERSION_MAJOR) << 24 | $(SW_VERSION_MINOR) << 16 | $(SW_VERSION_PATCH) << 8 | $(SW_VERSION_P) )))
endif
```
当version.mk中USE_SDK_VERSION := FALSE时，则版本由当前version.mk中配置决定。

并且版本信息会转换成一个32bit大小的数据用于存储。在版本防回滚校验中，会比较该32bit数据大小。转换关系如下：

基础版本在eFuse中存储，每个启动镜像会占用一个eFuse block(32bit)表示一个最基础的出厂版本。eFuse各个启动镜像对应的block如下，eFuse烧写参考《AX EFUSE使用说明.docx》。

| **Blk** | **rollback version image** |
| --- | --- |
| 6 | sbl version |
| 7 | rtos version |
| 8 | spl version |
| 9 | atf version |
| 10 | optee version |
| 11 | uboot version |
| 12 | kernel version |
| 13 | rootfs version |

每次当启动成功后可以查看当前启动镜像的版本对应转换后的值，并且启动脚本会把当前版本更新到升级版本中。

```
root@m57:~ # cat /proc/ax_proc/revision
Sbl Version 1507328
Rtos Version 1507328
Spl Version 1507328
Atf Version 1507328
Optee Version 1507328
Uboot Version 1507328
Kernel Version 1507328
```
# 8 Key Management

## 8.1 密钥类型

芯片运行中会涉及多个密钥，根据密钥在芯片中功能分成几类。

### 8.1.1 根密钥

根密钥是芯片密钥管理的基础，根密钥一般不会直接使用，而是通过根密钥派生别的密钥或用根密钥对别的密钥加密。根密钥存储在eFuse中，一芯一密，不可篡改。根密钥有比较严格的访问权限控制，只能由 HSM 访问。

| **Key Name** | **Description** |
| --- | --- |
| HUK | 存储在HSM OTP区域，可供 HSM 派生其他密钥。Safety域和Main域调用HSM HUK派生的密钥结果不同。 |
| RTK | 芯片的Root Key，存储在eFuse blk15-blk22中。用于加密镜像加密密钥 FEK，Safety域和Main域通过RTK可派生相同的密钥。 |

为了增加安全性，建议根密钥每个芯片烧写唯一的数据。根密钥的烧写方法可参考《AX EFUSE使用说明》。

### 8.1.2 公钥

公钥的作用是用来对签名做校验。在安全启动中，安全调试认证及OTA中都有使用，SDK默认使用同一个RSA公钥，在SDK中的路径如下：

| RSA密钥长度 | 私钥路径 | 公钥路径 |
| --- | --- | --- |
| RSA-2048 | tools/imgsign/private.pem | tools/imgsign/public.pem |
| RSA-3072 | tools/imgsign/key_3072/private.pem | tools/imgsign/key_3072/pubkey.pem |

在编译时会把公钥编译到软件镜像中，同样eFuse会存有公钥的hash区域，见《AX EFUSE使用说明》中1.6章节。eFuse中数据不可篡改，从而用来验证公钥的合法性。

### 8.1.3 静态密钥

静态密钥是指在 Axera 安全方案中存储于设备中的密钥，需要存储在 eFuse 或外部存储介质中。为了确保静态密钥不被泄露，静态密钥一般需要加密存储。

| **Key Name** | **Description** |
| --- | --- |
| FEK | 用来给启动镜像加密的对称密钥，通过RTK加密后存储在eFuse中。 |
| PEK | 用来给AI模型加密的对称密钥，通过HUK派生的密钥加密存储在外部存储介质中。 |

### 8.1.4 动态密钥

动态密钥是指在Axera设计的安全方案中，在设备中动态生成的密钥，动态密钥无需存储在存储介质中，可以是在HSM中，也可以是被Firewall保护的内存中。

| **Key Name** | **Description** |
| --- | --- |
| TEE HUK | TEE中的根密钥，由 HUK 派生生成，保存在TEE的运行内存中，可由 Firewall 保护。 |
| TEE FEK | TEE FEK是安全存储中实际给数据加密的密钥，每次加密会通过随机数生成一个新的FEK |
| KDK | 由HUK派生，存储在HSM中，可用来派生其他类型密钥。 |
| KEK | 可由HUK或KDK派生，存储在HSM中，HSM 使用 KEK 加密其他密钥，可实现对密钥的安全存储。 |

### 8.1.5 客户密钥

客户密钥由客户根据产品需求规划和生成。客户密钥需要安全存储，可以根据需求使用TEE安全存储或者HSM安全存储方案。在Safety域使用Autosar标准的Key management接口实现密钥的管理。Main 域可使用 HSM 接口完成密钥管理。客户密钥支持如下特性：

1. 支持密钥的真随机数生成
2. 支持密钥的安全存储
3. 支持密钥的派生
4. 支持密钥的生命周期设置
5. 支持密钥的导出
6. 支持密钥的删除

## 8.2 HSM密钥管理

在Main域调用HSM的API接口可实现密钥的管理，支持接口如下，详情参考《06 - AX HSM API 文档.docx》。

| **Interface** | **Description** |
| --- | --- |
| AX_HSM_KeyImport | Key的明文导入 |
| AX_HSM_KeyGenerate | Key的生成，支持真随机数生成对称密钥和非对称密钥 |
| AX_HSM_KeyExport | Key的导出 |
| AX_HSM_KeyCopy | Key的拷贝 |
| AX_HSM_KeyGetAttribute | 获取Key的属性 |
| AX_HSM_KeyDerive | Key的派生 |
| AX_HSM_KeyDynamicDelete | 存储在HSM内的动态Key的删除 |
| AX_HSM_KeyStaticDelete | 通过HSM静态安全存储的Key的删除 |

# 9 Lifecycle

## 9.1 生命周期概述

生命周期定义是指芯片从Axera出厂阶段，OEM/Tier1开发阶段，产品生产阶段，到产品维护阶段。不同阶段芯片中密钥的烧写，安全启动和安全调试可配置的状态。

| **生命周期** | **密钥管理** | **安全启动** | **安全调试** |
| --- | --- | --- | --- |
| Axera 出厂 | — | 普通启动 | 普通调试 |
| OEM/Tier1开发 | 用户key烧写 | 普通/安全启动 | 普通/安全调试 |
| 量产 | 用户key烧写 | 安全启动 | 安全调试 |
| 维护 | 用户key烧写 | 安全启动 | 安全调试 |