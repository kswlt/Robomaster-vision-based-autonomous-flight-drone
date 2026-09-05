#include <librealsense2/rs.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <set>
#include <string>
#include <vector>

namespace {
struct Stats {
  std::vector<double> values;
  void add(double value) { values.push_back(value); }
  double percentile(double p) const {
    if (values.empty()) return 0.0;
    auto sorted = values;
    std::sort(sorted.begin(), sorted.end());
    const auto index = static_cast<std::size_t>(std::ceil(p * sorted.size())) - 1;
    return sorted[std::min(index, sorted.size() - 1)];
  }
  double mean() const {
    return values.empty() ? 0.0 : std::accumulate(values.begin(), values.end(), 0.0) / values.size();
  }
};

void emit_stats(std::ostream& out, const char* name, const Stats& stats) {
  out << name << "_count," << stats.values.size() << '\n';
  out << name << "_mean_ms," << stats.mean() << '\n';
  out << name << "_median_ms," << stats.percentile(0.50) << '\n';
  out << name << "_p95_ms," << stats.percentile(0.95) << '\n';
  out << name << "_p99_ms," << stats.percentile(0.99) << '\n';
  out << name << "_max_ms," << stats.percentile(1.00) << '\n';
}
}  // namespace

int main(int argc, char** argv) {
  const double duration_s = argc > 1 ? std::stod(argv[1]) : 60.0;
  const std::string output = argc > 2 ? argv[2] : "d435_stereo_timing.csv";
  rs2::config config;
  config.disable_all_streams();
  config.enable_stream(RS2_STREAM_INFRARED, 1, 640, 480, RS2_FORMAT_Y8, 30);
  config.enable_stream(RS2_STREAM_INFRARED, 2, 640, 480, RS2_FORMAT_Y8, 30);
  rs2::pipeline pipeline;
  auto profile = pipeline.start(config);
  const auto start = std::chrono::steady_clock::now();
  double previous_left = -1.0, previous_right = -1.0;
  uint64_t frames = 0, left_duplicates = 0, right_duplicates = 0, left_backwards = 0, right_backwards = 0;
  Stats left_dt, right_dt, stereo_delta;
  std::set<int> timestamp_domains;
  while (std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() < duration_s) {
    auto frameset = pipeline.wait_for_frames(5000);
    auto left = frameset.get_infrared_frame(1);
    auto right = frameset.get_infrared_frame(2);
    if (!left || !right) continue;
    const double left_ts = left.get_timestamp();
    const double right_ts = right.get_timestamp();
    timestamp_domains.insert(static_cast<int>(left.get_frame_timestamp_domain()));
    timestamp_domains.insert(static_cast<int>(right.get_frame_timestamp_domain()));
    if (previous_left >= 0.0) {
      const double dt = left_ts - previous_left;
      left_dt.add(dt);
      if (dt == 0.0) ++left_duplicates;
      if (dt < 0.0) ++left_backwards;
    }
    if (previous_right >= 0.0) {
      const double dt = right_ts - previous_right;
      right_dt.add(dt);
      if (dt == 0.0) ++right_duplicates;
      if (dt < 0.0) ++right_backwards;
    }
    stereo_delta.add(std::abs(left_ts - right_ts));
    previous_left = left_ts;
    previous_right = right_ts;
    ++frames;
  }
  pipeline.stop();
  std::ofstream report(output);
  report << std::fixed << std::setprecision(3);
  report << "duration_s," << duration_s << '\n';
  report << "framesets," << frames << '\n';
  report << "left_fps," << frames / duration_s << '\n';
  report << "right_fps," << frames / duration_s << '\n';
  report << "left_duplicate_timestamps," << left_duplicates << '\n';
  report << "right_duplicate_timestamps," << right_duplicates << '\n';
  report << "left_backwards_timestamps," << left_backwards << '\n';
  report << "right_backwards_timestamps," << right_backwards << '\n';
  report << "timestamp_domain_values,";
  for (auto it = timestamp_domains.begin(); it != timestamp_domains.end(); ++it)
    report << (it == timestamp_domains.begin() ? "" : ";") << *it;
  report << '\n';
  emit_stats(report, "left_interval", left_dt);
  emit_stats(report, "right_interval", right_dt);
  emit_stats(report, "left_right_delta", stereo_delta);
  std::cout << "Wrote " << output << " with " << frames << " framesets\n";
}
