#include <librealsense2/rs.hpp>

#include <cmath>
#include <iomanip>
#include <iostream>

int main() {
  try {
    rs2::config config;
    config.disable_all_streams();
    config.enable_stream(RS2_STREAM_INFRARED, 1, 640, 480, RS2_FORMAT_Y8, 30);
    config.enable_stream(RS2_STREAM_INFRARED, 2, 640, 480, RS2_FORMAT_Y8, 30);
    rs2::pipeline pipeline;
    const auto profile = pipeline.start(config);
    const auto left = profile.get_stream(RS2_STREAM_INFRARED, 1).as<rs2::video_stream_profile>();
    const auto right = profile.get_stream(RS2_STREAM_INFRARED, 2).as<rs2::video_stream_profile>();
    const auto l = left.get_intrinsics();
    const auto r = right.get_intrinsics();
    const auto e = left.get_extrinsics_to(right);
    std::cout << std::fixed << std::setprecision(9);
    std::cout << "left_fx," << l.fx << "\nleft_fy," << l.fy << "\nleft_cx," << l.ppx << "\nleft_cy," << l.ppy << '\n';
    std::cout << "right_fx," << r.fx << "\nright_fy," << r.fy << "\nright_cx," << r.ppx << "\nright_cy," << r.ppy << '\n';
    std::cout << "translation_x_m," << e.translation[0] << "\ntranslation_y_m," << e.translation[1]
              << "\ntranslation_z_m," << e.translation[2] << '\n';
    std::cout << "baseline_m," << std::abs(e.translation[0]) << '\n';
    pipeline.stop();
  } catch (const rs2::error& error) {
    std::cerr << "RealSense error: " << error.what() << '\n';
    return 1;
  }
}
