#include <librealsense2/rs.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>

#include <chrono>
#include <cstring>
#include <memory>

class D435IrPublisher final : public rclcpp::Node {
 public:
  D435IrPublisher() : Node("d435_ir_publisher") {
    left_pub_ = create_publisher<sensor_msgs::msg::Image>("/d435/infra1/image_raw", rclcpp::SensorDataQoS());
    right_pub_ = create_publisher<sensor_msgs::msg::Image>("/d435/infra2/image_raw", rclcpp::SensorDataQoS());
    config_.disable_all_streams();
    config_.enable_stream(RS2_STREAM_INFRARED, 1, 640, 480, RS2_FORMAT_Y8, 30);
    config_.enable_stream(RS2_STREAM_INFRARED, 2, 640, 480, RS2_FORMAT_Y8, 30);
    pipeline_.start(config_);
    timer_ = create_wall_timer(std::chrono::milliseconds(1), [this] { publish_frames(); });
    RCLCPP_INFO(get_logger(), "D435 IR1/IR2 publisher ready: 640x480 Y8 @ 30 FPS; RGB/depth disabled");
  }

  ~D435IrPublisher() override { pipeline_.stop(); }

 private:
  void publish_one(const rs2::video_frame& frame, const rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr& pub,
                   const char* frame_id) {
    sensor_msgs::msg::Image message;
    // D435 GLOBAL_TIME is a RealSense frame measurement timestamp in milliseconds.
    const auto ns = static_cast<int64_t>(frame.get_timestamp() * 1e6);
    message.header.stamp = rclcpp::Time(ns, RCL_SYSTEM_TIME);
    message.header.frame_id = frame_id;
    message.height = frame.get_height();
    message.width = frame.get_width();
    message.encoding = "mono8";
    message.is_bigendian = false;
    message.step = frame.get_stride_in_bytes();
    message.data.resize(message.step * message.height);
    std::memcpy(message.data.data(), frame.get_data(), message.data.size());
    pub->publish(std::move(message));
  }

  void publish_frames() {
    rs2::frameset frames;
    if (!pipeline_.poll_for_frames(&frames)) return;
    auto left = frames.get_infrared_frame(1);
    auto right = frames.get_infrared_frame(2);
    if (left) publish_one(left, left_pub_, "d435_infra1");
    if (right) publish_one(right, right_pub_, "d435_infra2");
  }

  rs2::pipeline pipeline_;
  rs2::config config_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr left_pub_, right_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<D435IrPublisher>());
  rclcpp::shutdown();
  return 0;
}
