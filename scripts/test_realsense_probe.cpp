// test_realsense_probe.cpp — 只读探测 option range（确认 hwmon 0x2c 调用来源）
// 不执行任何写操作
#include <librealsense2/rs.hpp>
#include <iostream>
#include <vector>
#include <string>

using namespace rs2;

int main() {
    std::cout << "=== RealSense option-range probe (read-only) ===\n";
    try {
        context ctx;
        auto list = ctx.query_devices();
        if (list.size() == 0) { std::cout << "NO DEVICE\n"; return 1; }
        auto dev = list[0];
        std::cout << "Device: " << dev.get_info(RS2_CAMERA_INFO_NAME)
                  << " serial=" << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << "\n";
        auto sensors = dev.query_sensors();
        std::vector<rs2_option> opts = {
            RS2_OPTION_DEPTH_UNITS,
            RS2_OPTION_VISUAL_PRESET,
            RS2_OPTION_ENABLE_AUTO_EXPOSURE,
            RS2_OPTION_LASER_POWER,
            RS2_OPTION_EXPOSURE,
            RS2_OPTION_GAIN,
            RS2_OPTION_FRAMES_QUEUE_SIZE,
            RS2_OPTION_ENABLE_AUTO_WHITE_BALANCE
        };
        for (auto& s : sensors) {
            std::cout << "\n--- sensor: " << s.get_info(RS2_CAMERA_INFO_NAME) << " ---\n";
            for (auto o : opts) {
                try {
                    auto r = s.get_option_range(o);
                    std::cout << "  opt " << (int)o << ": min=" << r.min << " max=" << r.max
                              << " step=" << r.step << " def=" << r.def << " OK\n";
                } catch (const rs2::error& e) {
                    std::cout << "  opt " << (int)o << " FAIL: " << e.what() << "\n";
                }
            }
        }
        std::cout << "=== PROBE DONE ===\n";
        return 0;
    } catch (const rs2::error& e) {
        std::cout << "FATAL: " << e.what() << "\n";
        return 1;
    }
}
