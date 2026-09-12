#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIO 系统状态监控面板（SSH 中文交互版）
用法： ssh orangepi@192.168.137.210
      python3 ~/vio_status.py
"""
import glob
import os
import re
import select
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ---------- 颜色 ----------
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'


def ok(s):
    return f'{GREEN}✅ {s}{RESET}'


def bad(s):
    return f'{RED}❌ {s}{RESET}'


def warn(s):
    return f'{YELLOW}⚠️ {s}{RESET}'


# ---------- 基础检查 ----------
def proc_running(pattern):
    """进程是否在跑"""
    try:
        out = subprocess.run(['ps', 'aux'], capture_output=True, text=True,
                             timeout=5).stdout
        return any(p in out for p in pattern if p)
    except Exception:
        return False


def log_fresh(logfile, max_age=12):
    """日志文件最近更新（秒内）"""
    try:
        age = time.time() - os.path.getmtime(logfile)
        return age < max_age, age
    except Exception:
        return False, -1


def last_match(logfile, pattern):
    """取日志最后一条匹配行"""
    try:
        with open(logfile, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if pattern in line:
                    m = line
            return m
    except Exception:
        return None


def tail_has(logfile, pattern, n=30):
    """最近n行日志中是否有该模式（判断数据是否新鲜）"""
    try:
        with open(logfile, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-n:]
        return any(pattern in l for l in lines)
    except Exception:
        return False


# ---------- 状态面板 ----------
def status_panel():
    print()
    print(f'{BOLD}{CYAN}══════════ VIO 系统状态 ══════════{RESET}')
    print(f'{BOLD}{CYAN}  香橙派Pi5 · OpenVINS · PX4 v1.17{RESET}')
    print(f'{CYAN}══════════════════════════════════════{RESET}')

    # 1. RealSense 相机
    cam = proc_running(['realsense2_camera_node'])
    cam_fresh, cam_age = log_fresh('/tmp/camera.log')
    if cam:
        print(f'  {ok("RealSense D430 相机")}    (进程运行中)')
    elif cam_fresh:
        print(f'  {ok("RealSense D430 相机")}    (日志活跃 {cam_age:.0f}s前)')
    else:
        print(f'  {bad("RealSense D430 相机")}    未检测到运行')

    # 2. OpenVINS
    vio = proc_running(['run_subscribe_msckf'])
    vio_fresh, vio_age = log_fresh('/tmp/vio.log')
    if vio:
        print(f'  {ok("OpenVINS 视觉里程计")}    (进程运行中)')
    elif vio_fresh:
        print(f'  {ok("OpenVINS 视觉里程计")}    (日志活跃 {vio_age:.0f}s前)')
    else:
        print(f'  {bad("OpenVINS 视觉里程计")}    未检测到运行')

    # VIO 频率（从vio.log最后TIME行解析）
    vio_line = last_match('/tmp/vio.log', '[TIME]')
    if vio_line:
        mm = re.search(r'\(([\d.]+) hz', vio_line)
        if mm:
            print(f'  {CYAN}  └ 处理频率: {mm.group(1)} Hz{RESET}')

    # 3. 桥接节点
    br = proc_running(['vio_bridge_combined'])
    br_fresh, br_age = log_fresh('/tmp/vio_bridge.log')
    if br:
        print(f'  {ok("桥接节点 (MAVLink)")}    (进程运行中)')
    elif br_fresh:
        print(f'  {ok("桥接节点 (MAVLink)")}    (日志活跃 {br_age:.0f}s前)')
    else:
        print(f'  {bad("桥接节点 (MAVLink)")}    未检测到运行')

    # 4. 飞控连接（用glob展开通配符，subprocess的ls不经过shell不会展开*）
    acm_list = glob.glob('/dev/ttyACM*')
    acm = ' '.join(acm_list)
    if acm:
        print(f'  {ok("飞控连接")}           {acm}')
    else:
        print(f'  {bad("飞控连接")}           未检测到 /dev/ttyACM*')

    # 5. 视觉位置发送
    send_fresh = tail_has('/tmp/vio_bridge.log', '已发送VISION') and bool(acm)
    send_line = last_match('/tmp/vio_bridge.log', '已发送VISION')
    if send_line and send_fresh:
        mm = re.search(r'第(\d+)条', send_line)
        n = mm.group(1) if mm else '?'
        print(f'  {ok("视觉位置发送")}        已发送 {n} 条')
    elif send_line:
        mm = re.search(r'第(\d+)条', send_line)
        n = mm.group(1) if mm else '?'
        print(f'  {warn("视觉位置发送")}        已发送 {n} 条 (数据陈旧，飞控可能未连接)')
    else:
        print(f'  {bad("视觉位置发送")}        尚未发送')

    # 6. EKF 融合
    ekf_line = last_match('/tmp/vio_bridge.log', 'EKF状态')
    ekf_fresh = tail_has('/tmp/vio_bridge.log', 'EKF状态') and bool(acm)
    if ekf_line:
        vis_pos = 'True' in ekf_line.split('视位=')[1][:5] if '视位=' in ekf_line else False
        vis_vel = 'True' in ekf_line.split('视速=')[1][:5] if '视速=' in ekf_line else False
        mm = re.search(r'flags=(\d+)', ekf_line)
        flags = mm.group(1) if mm else '?'
        tag = f' (数据陈旧，飞控可能未连接)' if not ekf_fresh else ''
        if vis_pos:
            print(f'  {ok("EKF 视觉位置融合")}     已开启 (flags={flags}){tag}')
        else:
            print(f'  {bad("EKF 视觉位置融合")}     未开启 (flags={flags}){tag}')
        if vis_vel:
            print(f'  {ok("EKF 光流速度融合")}     已开启{tag}')
        else:
            print(f'  {bad("EKF 光流速度融合")}     未开启{tag}')
    else:
        print(f'  {bad("EKF 融合状态")}        无数据（飞控未连接或未收到状态）')

    # 7. 开机自启
    en = subprocess.run(['systemctl', 'is-enabled', 'vio.service'],
                        capture_output=True, text=True).stdout.strip()
    ac = subprocess.run(['systemctl', 'is-active', 'vio.service'],
                        capture_output=True, text=True).stdout.strip()
    if en == 'enabled' and ac == 'active':
        print(f'  {ok("开机自启服务")}        已启用且运行中')
    else:
        print(f'  {warn("开机自启服务")}      enabled={en} active={ac}')

    print(f'{CYAN}══════════════════════════════════════{RESET}')


# ---------- 数据查看 ----------
def get_xyz_vio():
    line = last_match('/tmp/vio_bridge.log', '已发送VISION')
    if not line:
        return '暂无数据（VIO未初始化，请晃动相机）'
    mm = re.search(r'x=([-\d.]+) y=([-\d.]+) z=([-\d.]+)', line)
    mm2 = re.search(r'r=([-\d.]+) p=([-\d.]+) y=([-\d.]+)', line)
    if mm:
        x, y, z = float(mm.group(1)), float(mm.group(2)), float(mm.group(3))
        s = f'x={x:8.3f}  y={y:8.3f}  z={z:8.3f} m'
        if mm2:
            s += f'   |  r={float(mm2.group(1)):7.1f} p={float(mm2.group(2)):7.1f} y={float(mm2.group(3)):7.1f}°'
        return s
    return '解析失败'


def get_xyz_ekf():
    line = last_match('/tmp/vio_bridge.log', 'EKF位置')
    if not line:
        return '暂无数据（飞控未输出本地位置）'
    mm = re.search(r'x=([-\d.]+) y=([-\d.]+) z=([-\d.]+)', line)
    mm2 = re.search(r'vx=([-\d.]+) vy=([-\d.]+) vz=([-\d.]+)', line)
    if mm:
        x, y, z = float(mm.group(1)), float(mm.group(2)), float(mm.group(3))
        s = f'x={x:8.3f}  y={y:8.3f}  z={z:8.3f} m'
        if mm2:
            s += f'   |  vx={float(mm2.group(1)):6.2f} vy={float(mm2.group(2)):6.2f} vz={float(mm2.group(3)):6.2f} m/s'
        return s
    return '解析失败'


def quit_pressed():
    """非阻塞检测键盘 q / Ctrl+C"""
    try:
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            return sys.stdin.read(1).strip().lower() == 'q'
    except Exception:
        pass
    return False


def show_live(what):
    """持续刷新显示"""
    getter = get_xyz_vio if what == 'vio' else get_xyz_ekf
    name = 'VIO输出 (NED)' if what == 'vio' else 'EKF位置 (飞控)'
    print(f'\n  {BOLD}实时查看: {name}{RESET}   (按 q 或 Ctrl+C 返回菜单)')
    try:
        while True:
            line = getter()
            print(f'\r  {line}   ', end='', flush=True)
            if quit_pressed():
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    print()


def show_live_rpy():
    print(f'\n  {BOLD}实时查看: 姿态 RPY (VIO输出){RESET}   (按 q 或 Ctrl+C 返回菜单)')
    try:
        while True:
            line = last_match('/tmp/vio_bridge.log', '已发送VISION')
            if line:
                mm = re.search(r'r=([-\d.]+) p=([-\d.]+) y=([-\d.]+)', line)
                if mm:
                    print(f'\r  roll={float(mm.group(1)):7.1f}°  pitch={float(mm.group(2)):7.1f}°  yaw={float(mm.group(3)):7.1f}°   ', end='', flush=True)
            if quit_pressed():
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    print()


def menu():
    print(f'\n{BOLD}选择查看内容{RESET}:')
    print(f'  {CYAN}1{RESET}  VIO输出位置 XYZ')
    print(f'  {CYAN}2{RESET}  EKF位置 XYZ (飞控融合结果)')
    print(f'  {CYAN}3{RESET}  姿态 RPY')
    print(f'  {CYAN}4{RESET}  刷新状态面板')
    print(f'  {CYAN}q{RESET}  退出')
    try:
        return input('  请选择: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 'q'


def main():
    print(f'{BOLD}{CYAN}VIO 状态监控已启动...{RESET}')
    while True:
        status_panel()
        choice = menu()
        if choice == '1':
            show_live('vio')
        elif choice == '2':
            show_live('ekf')
        elif choice == '3':
            show_live_rpy()
        elif choice == '4':
            continue
        elif choice == 'q':
            print('  再见！')
            break
        else:
            print('  无效选择')


if __name__ == '__main__':
    main()
