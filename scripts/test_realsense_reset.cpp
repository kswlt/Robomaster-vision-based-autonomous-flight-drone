// test_realsense_reset.cpp — 固件硬件复位测试（无破坏性：不清 EEPROM/校准，仅设备重启）
#include <librealsense2/rs.hpp>
#include <iostream>
#include <thread>
#include <chrono>

using namespace rs2;

int main() {
    std::cout << "=== RealSense hardware_reset test ===\n";
    try {
        context ctx;
        auto list = ctx.query_devices();
        if (list.size() == 0) { std::cout << "NO DEVICE before reset\n"; return 1; }
        auto dev = list[0];
        std::cout << "Before reset: " << dev.get_info(RS2_CAMERA_INFO_NAME)
                  << " serial=" << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << "\n";
        std::cout << "Issuing hardware_reset()...\n";
        dev.hardware_reset();
        std::cout << "reset issued, waiting 8s for re-enumeration...\n";
        std::this_thread::sleep_for(std::chrono::seconds(8));
        // 重新枚举
        for (int i = 0; i < 5; i++) {
            try {
                auto l2 = ctx.query_devices();
                if (l2.size() > 0) {
                    auto d2 = l2[0];
                    std::cout << "Re-enumerated: " << d2.get_info(RS2_CAMERA_INFO_NAME)
                              << " serial=" << d2.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << "\n";
                    auto sens = d2.query_sensors();
                    for (auto& s : sens) {
                        try {
                            auto r = s.get_option_range(RS2_OPTION_DEPTH_UNITS);
                            std::cout << "  Depth Units range OK: min=" << r.min << " max=" << r.max
                                      << " def=" << r.def << "\n";
                            std::cout << "  RESET RECOVERY: DEPTH UNITS READABLE — TRY STREAMS NEXT\n";
                        } catch (const rs2::error& e) {
                            std::cout << "  Depth Units still FAIL: " << e.what() << "\n";
                        }
                    }
                    return 0;
                }
                std::cout << "  (waiting for device, attempt " << i + 1 << ")...\n";
                std::this_thread::sleep_for(std::chrono::seconds(3));
            } catch (const rs2::error& e) {
                std::cout << "  query error (device mid-reset?): " << e.what() << "\n";
                std::this_thread::sleep_for(std::chrono::seconds(3));
            }
        }
        std::cout << "Device did not re-enumerate after reset.\n";
        return 1;
    } catch (const rs2::error& e) {
        std::cout << "FATAL: " << e.what() << "\n";
        return 1;
    }
}
