// test_realsense_depth_ir.cpp
// Minimal librealsense test: enable IR1 + IR2 + Depth simultaneously,
// run for 30 seconds, count frames and detect stalls.
#include <librealsense2/rs.hpp>
#include <iostream>
#include <chrono>
#include <thread>
#include <atomic>
#include <iomanip>

int main(int argc, char** argv) {
    int duration = 30;
    if (argc > 1) duration = std::atoi(argv[1]);

    std::cout << "=== D430 IR+Depth simultaneous test ===" << std::endl;
    std::cout << "Duration: " << duration << "s" << std::endl;

    rs2::context ctx;
    auto devices = ctx.query_devices();
    if (devices.size() == 0) {
        std::cerr << "ERROR: No RealSense device found!" << std::endl;
        return 1;
    }
    auto dev = devices[0];
    std::cout << "Device: " << dev.get_info(RS2_CAMERA_INFO_NAME) << std::endl;
    std::cout << "Serial: " << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << std::endl;
    std::cout << "FW: " << dev.get_info(RS2_CAMERA_INFO_FIRMWARE_VERSION) << std::endl;

    rs2::config cfg;
    cfg.enable_stream(RS2_STREAM_INFRARED, 1, 848, 480, RS2_FORMAT_Y8, 30);
    cfg.enable_stream(RS2_STREAM_INFRARED, 2, 848, 480, RS2_FORMAT_Y8, 30);
    cfg.enable_stream(RS2_STREAM_DEPTH, 424, 240, RS2_FORMAT_Z16, 6);

    rs2::pipeline pipe;
    std::cout << "Starting pipeline..." << std::endl;
    try {
        auto profile = pipe.start(cfg);
        std::cout << "Pipeline started successfully!" << std::endl;
        for (auto& s : profile.get_streams()) {
            auto vsp = s.as<rs2::video_stream_profile>();
            std::cout << "  Stream: " << rs2_stream_to_string(s.stream_type())
                      << " idx=" << (int)s.stream_index()
                      << " " << vsp.width() << "x" << vsp.height()
                      << "@" << s.fps() << "fps"
                      << " fmt=" << rs2_format_to_string(s.format()) << std::endl;
        }
    } catch (const rs2::error& e) {
        std::cerr << "ERROR starting pipeline: " << e.what() << std::endl;
        return 1;
    }

    std::atomic<int> ir1_count(0), ir2_count(0), depth_count(0);
    std::atomic<int> stall_count(0);
    std::atomic<bool> running(true);

    auto start = std::chrono::steady_clock::now();
    auto last_frame_time = std::chrono::steady_clock::now();

    std::cout << "Collecting frames for " << duration << "s..." << std::endl;

    while (running) {
        rs2::frameset frames;
        if (pipe.poll_for_frames(&frames)) {
            last_frame_time = std::chrono::steady_clock::now();
            for (auto f : frames) {
                if (f.is<rs2::video_frame>()) {
                    auto vf = f.as<rs2::video_frame>();
                    if (vf.get_profile().stream_type() == RS2_STREAM_INFRARED) {
                        if (vf.get_profile().stream_index() == 1) ir1_count++;
                        else ir2_count++;
                    } else if (vf.get_profile().stream_type() == RS2_STREAM_DEPTH) {
                        depth_count++;
                    }
                }
            }
        }

        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - start).count();
        auto since_last = std::chrono::duration_cast<std::chrono::seconds>(now - last_frame_time).count();

        if (since_last >= 5) {
            stall_count++;
            std::cout << "[" << elapsed << "s] STALL DETECTED: no frames for " << since_last << "s!" << std::endl;
            last_frame_time = now; // reset to avoid repeated warnings
        }

        if (elapsed >= duration) {
            running = false;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    auto total_elapsed = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::steady_clock::now() - start).count();

    std::cout << "\n=== RESULTS ===" << std::endl;
    std::cout << "Total time: " << total_elapsed << "s" << std::endl;
    std::cout << "IR1 frames: " << ir1_count << " (expected ~" << 30*total_elapsed << ")" << std::endl;
    std::cout << "IR2 frames: " << ir2_count << " (expected ~" << 30*total_elapsed << ")" << std::endl;
    std::cout << "Depth frames: " << depth_count << " (expected ~" << 6*total_elapsed << ")" << std::endl;
    std::cout << "Stalls detected: " << stall_count << std::endl;

    if (stall_count > 0 || ir1_count < 30*total_elapsed*0.5) {
        std::cout << "\nRESULT: FAIL - IR+Depth simultaneous causes frame stall/loss" << std::endl;
        pipe.stop();
        return 2;
    } else {
        std::cout << "\nRESULT: PASS - IR+Depth simultaneous stable" << std::endl;
        pipe.stop();
        return 0;
    }
}
