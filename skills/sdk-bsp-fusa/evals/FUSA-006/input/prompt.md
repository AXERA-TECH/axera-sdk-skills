# 客户提问（原始措辞）

> 我们 M57 Linux SDK，SDK 根目录 `/workspace/sdk/m57-linux`。
>
> 我们想把 happen 最大上报间隔从 1000ms 改成 200ms。按 FAQ 说的做法：
> 改源 Excel（`Fault_diagnosis_event_list.xlsx`）→ 重跑 `make PLAT=<我们的板型> fusa_config`
> → 把生成的 JSON 推到板子 → 重启 `ax_diag_service`。
>
> 服务启动没有任何报错，但板端回读还是 1000，行为也没变。
> 我们确认过 Excel 改动生效了（生成的 JSON 里就是 200），也确认过服务确实重启了。
> 是不是我们读 sysfs 的姿势不对？还是有别的开关没开？

## 后续回填：原始证据

（见 `evidence.txt`。）
