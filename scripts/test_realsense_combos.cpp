// test_realsense_combos.cpp
// Test which stream combinations D430 supports
#include <librealsense2/rs.hpp>
#include <iostream>
#include <vector>
#include <string>
#include <chrono>
#include <thread>

struct combo {
    std::string name;
    std::vector<rs2_stream> streams;
    std::vector<int> indices;
    std::vector<int> widths;
    std::vector<int> heights;
    std::vector<rs2_format> formats;
    std::vector<int> fps;
};

bool test_combo(const combo& c) {
    rs2::context ctx;
    auto devices = ctx.query_devices();
    if (devices.size() == 0) {
        std::cerr << "  No device!" << std::endl;
        return false;
    }
    rs2::config cfg;
    for (size_t i = 0; i < c.streams.size(); i++) {
        cfg.enable_stream(c.streams[i], c.indices[i], c.widths[i], c.heights[i], c.formats[i], c.fps[i]);
    }
    rs2::pipeline pipe;
    try {
        auto profile = pipe.start(cfg);
        // Collect 30 frames
        int count = 0;
        for (int i = 0; i < 60; i++) {
            rs2::frameset frames;
            if (pipe.poll_for_frames(&frames)) {
                count++;
                if (count >= 30) break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        pipe.stop();
        std::cout << "  OK (frames collected: " << count << ")" << std::endl;
        return true;
    } catch (const rs2::error& e) {
        std::cout << "  FAIL: " << e.what() << std::endl;
        return false;
    }
}

int main() {
    std::cout << "=== D430 Stream Combination Test ===" << std::endl;

    rs2::context ctx;
    auto devices = ctx.query_devices();
    if (devices.size() == 0) {
        std::cerr << "No RealSense device found!" << std::endl;
        return 1;
    }
    auto dev = devices[0];
    std::cout << "Device: " << dev.get_info(RS2_CAMERA_INFO_NAME)
              << " FW: " << dev.get_info(RS2_CAMERA_INFO_FIRMWARE_VERSION) << std::endl;

    std::vector<combo> combos = {
        {"IR1 only 848x480@30",
            {RS2_STREAM_INFRARED}, {1}, {848}, {480}, {RS2_FORMAT_Y8}, {30}},
        {"IR2 only 848x480@30",
            {RS2_STREAM_INFRARED}, {2}, {848}, {480}, {RS2_FORMAT_Y8}, {30}},
        {"IR1+IR2 848x480@30",
            {RS2_STREAM_INFRARED, RS2_STREAM_INFRARED}, {1,2}, {848,848}, {480,480}, {RS2_FORMAT_Y8,RS2_FORMAT_Y8}, {30,30}},
        {"Depth only 480x270@15",
            {RS2_STREAM_DEPTH}, {0}, {480}, {270}, {RS2_FORMAT_Z16}, {15}},
        {"Depth only 424x240@6",
            {RS2_STREAM_DEPTH}, {0}, {424}, {240}, {RS2_FORMAT_Z16}, {6}},
        {"IR1+Depth 848x480@30 + 424x240@6",
            {RS2_STREAM_INFRARED, RS2_STREAM_DEPTH}, {1,0}, {848,424}, {480,240}, {RS2_FORMAT_Y8,RS2_FORMAT_Z16}, {30,6}},
        {"IR1+IR2+Depth 848x480@30 + 424x240@6",
            {RS2_STREAM_INFRARED, RS2_STREAM_INFRARED, RS2_STREAM_DEPTH}, {1,2,0}, {848,848,424}, {480,480,240}, {RS2_FORMAT_Y8,RS2_FORMAT_Y8,RS2_FORMAT_Z16}, {30,30,6}},
        {"IR1+IR2+Depth 848x480@30 + 480x270@15",
            {RS2_STREAM_INFRARED, RS2_STREAM_INFRARED, RS2_STREAM_DEPTH}, {1,2,0}, {848,848,480}, {480,480,270}, {RS2_FORMAT_Y8,RS2_FORMAT_Y8,RS2_FORMAT_Z16}, {30,30,15}},
    };

    int pass = 0, fail = 0;
    for (auto& c : combos) {
        std::cout << "\n[" << c.name << "]" << std::endl;
        if (test_combo(c)) pass++;
        else fail++;
    }

    std::cout << "\n=== SUMMARY: " << pass << " passed, " << fail << " failed ===" << std::endl;
    return 0;
}
