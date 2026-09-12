// test_realsense_streams.cpp — 最小 librealsense 测试（绕过 ROS）
// 用法: 停掉 vio.service 后运行
//   1. 枚举 device/sensor/profile
//   2. Test A-E 依次启动保守 profile，收帧，输出精确异常
#include <librealsense2/rs.hpp>
#include <iostream>
#include <vector>
#include <string>
#include <thread>
#include <chrono>
#include <map>

using namespace rs2;

static std::string dev_info_safe(device& dev, rs2_camera_info info) {
    try {
        std::string v = dev.get_info(info);
        return v.empty() ? "(empty)" : v;
    } catch (const rs2::error& e) {
        return "(ERR: " + std::string(e.what()) + ")";
    }
}

static void print_dev_info(device& dev) {
    std::cout << "  Name              : " << dev_info_safe(dev, RS2_CAMERA_INFO_NAME) << "\n";
    std::cout << "  Serial Number     : " << dev_info_safe(dev, RS2_CAMERA_INFO_SERIAL_NUMBER) << "\n";
    std::cout << "  Firmware Version  : " << dev_info_safe(dev, RS2_CAMERA_INFO_FIRMWARE_VERSION) << "\n";
    std::cout << "  Rec. FW Version   : " << dev_info_safe(dev, RS2_CAMERA_INFO_RECOMMENDED_FIRMWARE_VERSION) << "\n";
    std::cout << "  Product Id        : " << dev_info_safe(dev, RS2_CAMERA_INFO_PRODUCT_ID) << "\n";
    std::cout << "  Camera Locked     : " << dev_info_safe(dev, RS2_CAMERA_INFO_CAMERA_LOCKED) << "\n";
    std::cout << "  USB Type Desc     : " << dev_info_safe(dev, RS2_CAMERA_INFO_USB_TYPE_DESCRIPTOR) << "\n";
    std::cout << "  ASIC Serial Number: " << dev_info_safe(dev, RS2_CAMERA_INFO_ASIC_SERIAL_NUMBER) << "\n";
    std::cout << "  FW Update Id      : " << dev_info_safe(dev, RS2_CAMERA_INFO_FIRMWARE_UPDATE_ID) << "\n";
    std::cout << "  Physical Port     : " << dev_info_safe(dev, RS2_CAMERA_INFO_PHYSICAL_PORT) << "\n";
    std::cout << "  Advanced Mode     : " << dev_info_safe(dev, RS2_CAMERA_INFO_ADVANCED_MODE) << "\n";
    std::cout << "  Product Line      : " << dev_info_safe(dev, RS2_CAMERA_INFO_PRODUCT_LINE) << "\n";
}

// 找某 sensor 上指定 stream 类型+index 的最保守 profile（最小分辨率、最低fps）
static std::vector<stream_profile> pick_profiles(sensor& s, const std::vector<std::pair<rs2_stream,int>>& want) {
    std::vector<stream_profile> out;
    auto profiles = s.get_stream_profiles();
    for (auto& w : want) {
        stream_profile best;
        int best_score = -1;
        for (auto& p : profiles) {
            if (!p.is<video_stream_profile>()) continue;
            auto v = p.as<video_stream_profile>();
            if (v.stream_type() != w.first) continue;
            if (w.second != 0 && v.stream_index() != w.second) continue;
            int score = v.width() * v.height() * v.fps(); // 保守=最小
            if (best_score < 0 || score < best_score) { best = p; best_score = score; }
        }
        if (best_score >= 0) out.push_back(best);
    }
    return out;
}

static std::string prof_str(const stream_profile& p) {
    auto v = p.as<video_stream_profile>();
    std::string sn = (v.stream_type() == RS2_STREAM_INFRARED) ? "IR" : "Depth";
    return sn + std::to_string(v.stream_index()) + " " + std::to_string(v.width()) + "x"
           + std::to_string(v.height()) + "@" + std::to_string(v.fps());
}

int main() {
    std::cout << "=== RealSense minimal test (librealsense 2.58.3, no ROS) ===\n";
    try { log_to_console(RS2_LOG_SEVERITY_DEBUG); } catch (...) {}

    try {
        context ctx;
        auto list = ctx.query_devices();
        std::cout << "Devices found: " << list.size() << "\n";
        if (list.size() == 0) { std::cout << "NO DEVICE — exit\n"; return 1; }
        auto dev = list[0];
        print_dev_info(dev);

        auto sensors = dev.query_sensors();
        std::cout << "\n=== SENSORS & PROFILES ===\n";
        sensor* stereo = nullptr;
        for (auto& s : sensors) {
            std::string sn = s.get_info(RS2_CAMERA_INFO_NAME);
            std::cout << "Sensor: " << sn << "\n";
            for (auto& p : s.get_stream_profiles()) {
                if (p.is<video_stream_profile>()) {
                    auto v = p.as<video_stream_profile>();
                    std::cout << "    profile: stream=" << v.stream_type() << " idx=" << v.stream_index()
                              << " fmt=" << v.format() << " " << v.width() << "x" << v.height()
                              << "@" << v.fps() << "\n";
                }
            }
            if (sn.find("Stereo") != std::string::npos) stereo = &s;
            if (!stereo && sn.find("Depth") != std::string::npos) stereo = &s;
            if (!stereo && sn.find("RGB") != std::string::npos) {} // ignore
        }
        if (!stereo && sensors.size() > 0) stereo = &sensors[0];
        if (!stereo) { std::cout << "NO USABLE SENSOR\n"; return 1; }

        std::cout << "\n=== STREAM START TESTS (on sensor: " << stereo->get_info(RS2_CAMERA_INFO_NAME) << ") ===\n";

        struct TC { std::string name; std::vector<std::pair<rs2_stream,int>> want; int secs; };
        std::vector<TC> tests = {
            {"Test A: infra1 only ", {{RS2_STREAM_INFRARED, 1}}, 4},
            {"Test B: infra2 only ", {{RS2_STREAM_INFRARED, 2}}, 4},
            {"Test C: infra1+infra2", {{RS2_STREAM_INFRARED, 1}, {RS2_STREAM_INFRARED, 2}}, 4},
            {"Test D: depth only  ", {{RS2_STREAM_DEPTH, 0}}, 4},
            {"Test E: IR1+IR2+depth", {{RS2_STREAM_INFRARED, 1}, {RS2_STREAM_INFRARED, 2}, {RS2_STREAM_DEPTH, 0}}, 5},
        };

        for (auto& t : tests) {
            std::cout << "\n----------------------------------------\n" << t.name << "\n";
            try {
                auto profs = pick_profiles(*stereo, t.want);
                if (profs.empty()) { std::cout << "  [FAIL] no matching profile available\n"; continue; }
                std::cout << "  requested:";
                for (auto& p : profs) std::cout << " [" << prof_str(p) << "]";
                std::cout << "\n";
                long frames = 0;
                std::string first_fmt;
                stereo->open(profs);
                stereo->start([&](frame f) { frames++; });
                std::this_thread::sleep_for(std::chrono::seconds(t.secs));
                stereo->stop();
                stereo->close();
                std::cout << "  [PASS] started OK, frames in " << t.secs << "s: " << frames
                          << " (~" << (frames / t.secs) << " fps)\n";
            } catch (const rs2::error& e) {
                try { stereo->stop(); } catch (...) {}
                try { stereo->close(); } catch (...) {}
                std::cout << "  [FAIL] rs2::error: " << e.what() << "\n";
            } catch (const std::exception& e) {
                try { stereo->stop(); } catch (...) {}
                try { stereo->close(); } catch (...) {}
                std::cout << "  [FAIL] std::exception: " << e.what() << "\n";
            }
        }

        std::cout << "\n=== DONE ===\n";
        return 0;
    } catch (const rs2::error& e) {
        std::cout << "FATAL rs2::error: " << e.what() << "\n";
        return 1;
    } catch (const std::exception& e) {
        std::cout << "FATAL: " << e.what() << "\n";
        return 1;
    }
}
