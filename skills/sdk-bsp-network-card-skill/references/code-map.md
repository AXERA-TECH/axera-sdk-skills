# AX615 网络代码与取证地图

- 代码基线：`kernel/linux/linux-4.19.125`
- MAC/MDIO：`kernel/linux/linux-4.19.125/drivers/net/ethernet/stmicro/stmmac/`
- AXERA glue：`dwmac-axera.c`、`dwmac-axera-plat.c`
- PHY：`kernel/linux/linux-4.19.125/drivers/net/phy/axera-ephy.c`
- 关键符号：`ax_ephy_config_init`、`ax_ephy_reg_dump`、`ephy_show_regdump`、`ephy_store_regdump`、`genphy_read_status`、`stmmac_mdio`
- TCP 吞吐：`kernel/linux/linux-4.19.125/net/ipv4/tcp_bbr.c`；CUBIC 位于同一目录

## 现场命令

先确认接口名并保留原始输出；需要 root 的命令应注明权限。

```sh
ip -d link show eth0
ethtool eth0
ethtool -i eth0
ethtool -S eth0
cat /sys/class/net/eth0/carrier
cat /sys/class/net/eth0/phydev/regdump
dmesg -T | grep -Ei 'stmmac|phy|eth|link|mdio|timeout|reset'
ip addr show dev eth0
ip route
ss -lntp
cat /proc/sys/net/ipv4/tcp_congestion_control
zcat /proc/config.gz 2>/dev/null | grep CONFIG_HZ || true
```

PHY sysfs 调试只在确认节点存在、记录原值并具备恢复方案后使用；不要在量产设备上盲写寄存器。
