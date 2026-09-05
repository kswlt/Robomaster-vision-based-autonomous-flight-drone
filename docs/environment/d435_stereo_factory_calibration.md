# D435 双目工厂标定（Pure Stereo VO 输入）

采集日期：2026-09-05。设备：Intel RealSense D435，序列号 `938422073656`，固件 `5.17.3.10`。本记录只覆盖 IR1/IR2 的 `640x480`、`Y8`、30 Hz 工作档，不启用 RGB、深度或点云。

## 导出结果

`rs-enumerate-devices -c` 在 NX 当前运行相机预览时可无侵入读取设备标定：

| 项目 | 值 |
| --- | ---: |
| IR1 fx / fy | 382.384521484375 / 382.384521484375 px |
| IR1 cx / cy | 319.303405761719 / 240.187591552734 px |
| IR2 内参 | 与 IR1 相同 |
| IR1 → IR2 旋转 | 单位矩阵 |
| IR1 → IR2 平移 | (-0.0501375198364258, 0, 0) m |
| 基线绝对值 | 0.0501375198364258 m |
| `bf`（由 ORB-SLAM3 计算） | 19.171811531065 px·m |

这些值已写入 [`config/orb_slam3/d435_stereo_640x480.yaml`](../../config/orb_slam3/d435_stereo_640x480.yaml)，作为 ORB-SLAM3 Stereo 的首个参数基线。该 ORB-SLAM3 版本由 `Stereo.T_c1_c2` 读取右相机到左相机的变换，因此配置中的 X 平移为正基线；`bf` 在运行时由该矩阵的模长和 `fx` 计算。

## 可复现导出

[`tools/d435_stereo_calibration_export.cpp`](../../tools/d435_stereo_calibration_export.cpp) 使用已验证的 V4L2 librealsense 安装路径运行。它需要独占相机，因此应在停止本项目的 D435 发布节点后执行；不要停止用户原有的其他相机或 Foxglove 服务。

```bash
g++ -O2 -std=c++17 d435_stereo_calibration_export.cpp \
  -I/home/nvidia/opt/librealsense-v4l2-2.58.4/include \
  -L/home/nvidia/opt/librealsense-v4l2-2.58.4/lib -lrealsense2 \
  -Wl,-rpath,/home/nvidia/opt/librealsense-v4l2-2.58.4/lib \
  -o d435_stereo_calibration_export
./d435_stereo_calibration_export
```

## 尚待验证

工厂内外参和零相对旋转支持把该 IR 对作为已对齐的双目输入；但这不是飞行级验证。开始 ORB-SLAM3 前仍需完成：左右帧配对与时间戳策略、实景特征/尺度稳定性、遮挡和快速运动下的失跟恢复，以及在地面测试中验证图像行对齐。不得据此解锁或起飞。
