# 冻结报告：运行态 VIO 配置与哈希（2026-09-23）

> 本文件记录**修改前**的真实运行态。任何"某个 commit 说修好了"的说法，都必须先与本表
> 对照才能采信。
>
> 冻结时刻：`2026-09-23T12:18:17+08:00`
> 冻结产物：`/home/orangepi/vio_audit_freeze_20260923T121817.tar.gz`（含运行日志、
> 全部脚本副本、`/etc/systemd/system` 单元、`lsusb -t`、温度与频率）

```
git rev-parse HEAD            4310ada593eb81b55a550dae83f758c8d22655cf
git rev-parse origin/d430     4310ada593eb81b55a550dae83f758c8d22655cf   (0/0 分歧)
git status                    11 个文件 modified，但 diffstat = 0 insertions/0 deletions
                              → 纯 CRLF 行尾差异，无内容改动
```

> 网络注记：本机 `git` 全局配置了失效代理 `http://127.0.0.1:64084`，
> `git fetch` 会失败。可用
> `git -c http.proxy= -c https.proxy= fetch origin` 直连成功。

---

## 1. 运行配置目录（**不是 git 仓库**）

`/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430/`

| SHA256 | 文件 | 备注 |
|---|---|---|
| `7dc4b109586dae32597ba0a362fa08d6b43a1c543e9d677077f82b93264b8d61` | `estimator_config.yaml` | **与 git HEAD 一致** |
| `33544c129f26bb020be01e4edea3969d3443c13ca544e919dd844ff0ee964540` | `kalibr_imucam_chain.yaml` | **timeshift = −0.010**；与 git `fcfc2457…`（+0.001256）**不一致** |
| `9c4c822244430d0d65979085063acde0e1dfc0d77c82e0a495598d36629a048d` | `kalibr_imu_chain.yaml` | 与 git HEAD 一致 |
| `0453e70813f33562100f8ae60138c67704559f24af14960e54078dedc2853bca` | `kalibr_imucam_chain.nominal.yaml` | 旁支 |
| `fcfc24571c23bf22e7a5c05661a3204402b8f26b7456071855e0255c73305c46` | `…bak-neg08deg-20260923022816` | **与 git HEAD 的 `kalibr_imucam_chain.yaml` 同哈希** |
| `db9fb580cf59f07f86b70074e059bf17be9a1bb6981241a44d4834e89646e9be` | `…bak-7deg-20260923024126` | 手工调参 |
| `543c2c0abdd351c880cc53d08a8e36df7568eac5245e477fee0489f9c4344b28` | `…bak-int640-20260923022511` | 手工调参 |
| `a9f819f149d019ebdb379ad792623a8190ee58ffdc2052be2bf1bf79f9c19ca1` | `…bak-inv7-20260923033201` | 手工调参 |
| `9e600110ffa9ca485ad7a3b22a98158d49d6fec930fe4000818acc29c3e27fa0` | `…bak-mangled-20260923025152` | 手工调参 |
| `af3b247b5ecb85d2f5c0aec040fefe432ccfb077408e83636f04216047613869` | `…bak-ts010` | 手工调参 |
| `fdf52630f597ff981d794bc0107eb717a2a0405b32b061cf6760854226ba37ab` | `…bak-20260919` | 手工调参 |

**运行进程实际加载值（OpenVINS 自己打印，非推断）**：

```
LOADED_CONFIG_PATH=/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430/estimator_config.yaml
LOADED_CAMERA_IMU_TIME_OFFSET_SEC=-0.010000000
LOADED_CAMERA_0_INTRINSICS=422.216 422.216 423.231 240.207 0 0 0 0
   EXTRINSICS_Q_ItoC_P_IinC=-0.500805 0.506195 -0.493205 0.49971 0.0222792 0.0226863 -0.076766
LOADED_CAMERA_1_INTRINSICS=422.216 422.216 423.231 240.207 0 0 0 0
   EXTRINSICS_Q_ItoC_P_IinC=-0.500627 0.505289 -0.493487 0.500526 -0.0246902 0.0224388 -0.0779234
```

---

## 2. 启动脚本与 systemd 单元：5 套并存

| SHA256 | 路径 |
|---|---|
| `7d98dd54f5a2594f6990cf62e326d698f0d9cabeadc01a54ea3849c72f11292b` | `/home/orangepi/kswlt/vio_ws/start_vio.sh` ← **内容错误**（640×480、`imu_bridge.py`、`vio_to_px4.py`） |
| `4a0556068a37ef0a78238a8dd6e70764aedf6353e96afb9255d002b3ba488162` | `/home/orangepi/kswlt/vio_ws/run_vio.sh` |
| `2e335a42f2aafe5fbc38e9d931e554ffec77d91b7a6dff11737182b34d791fed` | `/home/orangepi/kswlt/tools/start_vio.sh` |
| `2e335a42f2aafe5fbc38e9d931e554ffec77d91b7a6dff11737182b34d791fed` | `/home/orangepi/kswlt/gh_d430/start_vio.sh` |
| `2e335a42f2aafe5fbc38e9d931e554ffec77d91b7a6dff11737182b34d791fed` | `/home/orangepi/kswlt/vio-improve/start_vio.sh` |
| `24b6a43c7efec62de965edecb7b39f226ebde892775010e5dfa513180b6a4b9e` | git HEAD `start_vio_systemd.sh` == `gh_d430` == `vio-improve` |
| **`37c413676e63dc8c3ab8deae914cd714b668d3322e8a0b3721854f14a143da88`** | **`/home/orangepi/kswlt/tools/start_vio_systemd.sh`** ← **systemd 真正执行的版本，git 里没有** |
| `7223256a001f6b66f5c93dbec0ecdb0c7b70d9e97dca24b4c0f80841995ed51e` | **`/etc/systemd/system/vio.service`** ← ≠ git `4ab96de1…` |
| `aa173ca8f0e7a973c247d5a37dc9beecdabb8b2b694ecf774d8977e488c94993` | `/etc/systemd/system/vio-watchdog.service` == git |

`/etc/systemd/system/vio.service` 内容：

```ini
[Service]
User=orangepi
WorkingDirectory=/home/orangepi
ExecStart=/home/orangepi/kswlt/tools/start_vio_systemd.sh
```

冻结时 `vio.service` = **disabled / inactive**，即当时的运行栈是手工拉起的
（`PPID=1`，stdout/stderr 重定向到 `/tmp/vio_audit.log` 等）。

---

## 3. `vio_bridge_combined.py`：4 个版本

| SHA256 | 路径 | 判定 |
|---|---|---|
| `214794d2682d7dee5194837e339d435bd847084015c05611793ebc795b1e5883` | `vio_ws/vio_bridge/`（**运行中**） | == git HEAD ✅ |
| `be4ef772717d6a35ae9f5fd0f23ab96a07a66b0cc09f643408bf3745f11532de` | `gh_d430/`、`vio-improve/` | 陈旧 |
| `aa4a23fb5c2ac1c02a9c77610528f4858c375d5808595370e544592d468f6870` | `tools/` | 第三种 |

---

## 4. OpenVINS 源码：仅 ZUPT 被本地修改

上游 OpenVINS 文件时间戳均为 `Nov 30 2025`；唯独：

```
-rw-rw-r-- 16550 Sep 13 16:49 UpdaterZeroVelocity.cpp     ← 被改过
-rw-rw-r--  6046 Sep 13 16:49 UpdaterZeroVelocity.h       ← 被改过
```

| SHA256 | 文件 |
|---|---|
| `d7858e493d848366ad75e61475b337732ae893fedaf3e2c99f71f18cd939ff66` | `ov_msckf/src/update/UpdaterZeroVelocity.cpp` |
| `76b2d00ae99b4c1bb33a478283d169823be0120a96f4cd3ed024460ee7bfba72` | `ov_msckf/src/update/UpdaterZeroVelocity.h` |
| `d73a3586ec22c6011a1c50cfe534a65de454e1b3df2d6c23a1f4e4dae4d0ce9e` | `ov_msckf/src/core/VioManager.cpp` |
| `3b7013545bed435568ddae4959d96e6fc5e7a0b260ec864828d30a2406e482d5` | `ov_msckf/src/ros/ROS2Visualizer.cpp` |
| `9c0113c7acab30b5d98efc0368217031af64ad3b23d64bac924ad373f2f83511` | `ov_init/src/static/StaticInitializer.cpp` |
| `7cfdc9a14c495a1fdf5071fd344536b4d0edc8c31af00e6ee9df7bd3f943ca14` | `ov_msckf/src/run_subscribe_msckf.cpp`（含本地添加的 `LOADED_*` 打印） |
| `cfadc4b4d3452893a53e4f425ab16dc2c5cc766867bcd7b6ae493df3928e9458` | `install/ov_msckf/lib/ov_msckf/run_subscribe_msckf`（实际运行二进制） |

本地 `UpdaterZeroVelocity.cpp` 与两份 `.before` 备份的关键差异见
`VIO_VALIDATED_BASELINE.md` §3.2。

---

## 5. 进程运行环境（`/proc/PID/environ`，全部一致）

```
ROS_DISTRO=humble
ROS_DOMAIN_ID=42
ROS_LOCALHOST_ONLY=1        ← 关键：新进程若用默认 0 则完全发现不到任何节点/话题
```

启动方式（实测 cmdline）：

```
realsense2_camera_node --ros-args -r __node:=camera -r __ns:=/camera \
    --params-file /tmp/launch_params_z6f9mv6m --params-file /tmp/launch_params_fsigcme7

python3 …/vio_bridge_combined.py --ros-args -p serial_port:=/dev/ttyACM0 \
    -p send_vision_to_px4:=false

…/run_subscribe_msckf --ros-args \
    -p config_path:=…/config/d430/estimator_config.yaml -p publish_tf:=false

foxglove_bridge --ros-args -p topic_filter:=[/odomimu_viz,/trajectory,/tf_static]
```

**`/tmp/launch_params_z6f9mv6m`（相机实际收到的参数）中不存在
`depth_module.emitter_enabled`、`depth_module.laser_power` 等键**，且
`/opt/ros/humble/share/realsense2_camera/launch/rs_launch.py` 中不存在
`enable_ir_emitter` 参数 → 历史脚本的 `enable_ir_emitter:=false` 从未生效。

另有一个常驻 web 可视化进程：

```
python3 server.py   cwd=/tmp/viz_web   LISTEN 0.0.0.0:8080   累计均摊 ≈21% CPU
```

---

## 6. 硬件实测

```
D430:  Bus 002 Device 003  ID 8086:0ad4   → 5000M SuperSpeed ✅
PX4 :  Bus 007 Device 003  ID 1b8c:0036 MicoAir743AIO → cdc_acm 12M (USB FS)
Stereo Baseline (硬件): 50.137516 mm
Exposure 范围: 1..165000, 默认 8500      Gain 范围: 16..248, 默认 16
emitter_enabled 默认 1, laser_power 默认 150, emitter_always_on 0
```

---

## 7. 冻结时使用的 immutable bag

| Bag | 时长 | /imu | 图像 | 相机率 | IMU 率 | SHA256 |
|---|---|---|---|---|---|---|
| `20260922T235522Z_LASEROFF3/bag` | 64.35 s | 12613 | 1931 | 29.99 Hz | 198.6 Hz | `668e1148ce5e5b4642ad5af5cb2022537669d72630ce908e55d9f5a78ee7d23a` |
| `20260922T194503Z_LASEROFF` | 69.3 s | — | — | — | — | `5db109e3270440db834deb8ca460ee96b248bb83ec4b94f796a95b47c7d3cdd6` |
| `20260922T195104Z_LASEROFF2` | 79.6 s | — | — | — | — | `eefe759e7ae5a45e5bc679f7331b19aee26f8f17b0ec53f761827016d6c91fbf` |
| `20260922T191022_360Z_DYN50E/bag` | 149.3 s | 29117 | 4479 | 30.00 Hz | 195.0 Hz | `94d04d0d27a2578437b6c714eff8c4de8c6f1db2a9a72beeabff036595d67752` |
| `20260922T180933_210Z_DYN50/bag` | 62.0 s | — | — | — | — | `a57eed34a596c79cf26b92decef21141b5f18f88f2d23e24c9c62c3d0d065a43` |

**本文件的"LASEROFF"/"DYN50"仅是文件名，不是投影器状态的证据。**
实测各 bag 首帧的亮度特征见 `VIO_VALIDATED_BASELINE.md` §3.1。
