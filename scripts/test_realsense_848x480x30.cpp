// test848.cpp — 快速验证 D430 848x480@30 (IR1+IR2)，收帧统计
#include <librealsense2/rs.hpp>
#include <iostream>
#include <vector>
#include <thread>
#include <chrono>

using namespace rs2;

int main() {
    std::cout << "=== D430 848x480@30 stereo test ===\n";
    try {
        context ctx;
        auto list = ctx.query_devices();
        if (list.size() == 0) { std::cout << "NO DEVICE\n"; return 1; }
        auto dev = list[0];
        std::cout << "Device: " << dev.get_info(RS2_CAMERA_INFO_NAME)
                  << " serial=" << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER)
                  << " fw=" << dev.get_info(RS2_CAMERA_INFO_FIRMWARE_VERSION) << "\n";
        auto sensors = dev.query_sensors();
        sensor* stereo = nullptr;
        for (auto& s : sensors) {
            std::string n = s.get_info(RS2_CAMERA_INFO_NAME);
            if (n.find("Stereo") != std::string::npos) stereo = &s;
        }
        if (!stereo) { std::cout << "NO STEREO SENSOR\n"; return 1; }

        std::vector<stream_profile> want;
        for (auto& p : stereo->get_stream_profiles()) {
            if (!p.is<video_stream_profile>()) continue;
            auto v = p.as<video_stream_profile>();
            if (v.stream_type() == RS2_STREAM_INFRARED &&
                (v.stream_index() == 1 || v.stream_index() == 2) &&
                v.width() == 848 && v.height() == 480 && v.fps() == 30 && v.format() == RS2_FORMAT_Y8) {
                want.push_back(p);
            }
        }
        if (want.size() != 2) {
            std::cout << "848x480@30 Y8 profiles found: " << want.size() << " (expected 2)\n";
            return 1;
        }
        long f1 = 0, f2 = 0;
        stereo->open(want);
        stereo->start([&](frame f) {
            if (f.get_profile().stream_index() == 1) f1++;
            else f2++;
        });
        std::cout << "streaming 8s...\n";
        std::this_thread::sleep_for(std::chrono::seconds(8));
        stereo->stop();
        stereo->close();
        std::cout << "infra1 frames: " << f1 << "  (~" << (f1 / 8) << " fps)\n";
        std::cout << "infra2 frames: " << f2 << "  (~" << (f2 / 8) << " fps)\n";
        std::cout << (f1 >= 200 && f2 >= 200 ? "[PASS] 848x480@30 stable" : "[CHECK] fps below 25, inspect") << "\n";
        return 0;
    } catch (const rs2::error& e) {
        std::cout << "FAIL: " << e.what() << "\n";
        return 1;
    }
}
