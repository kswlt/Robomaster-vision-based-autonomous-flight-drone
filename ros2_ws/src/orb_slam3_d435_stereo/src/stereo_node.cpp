// SPDX-License-Identifier: GPL-3.0-or-later
// Ground-only D435 IR stereo adapter for ORB-SLAM3. It neither opens MAVLink nor controls PX4.

#include <chrono>
#include <memory>
#include <mutex>
#include <string>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/sync_policies/approximate_time.h>
#include <message_filters/synchronizer.h>
#include <nav_msgs/msg/path.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/int32.hpp>
#include <tf2_ros/transform_broadcaster.h>

#include <opencv2/core.hpp>

#include "System.h"
#include "Tracking.h"

class StereoNode : public rclcpp::Node {
 public:
  using Image = sensor_msgs::msg::Image;
  using SyncPolicy = message_filters::sync_policies::ApproximateTime<Image, Image>;

  StereoNode() : Node("orb_slam3_d435_stereo") {
    declare_parameter<std::string>("vocab", "");
    declare_parameter<std::string>("settings", "");
    declare_parameter<std::string>("left_topic", "/d435/infra1/image_raw");
    declare_parameter<std::string>("right_topic", "/d435/infra2/image_raw");
    declare_parameter<bool>("use_viewer", false);
    const auto vocab = get_parameter("vocab").as_string();
    const auto settings = get_parameter("settings").as_string();
    if (vocab.empty() || settings.empty()) {
      RCLCPP_ERROR(get_logger(), "set vocab and settings parameters before starting");
      rclcpp::shutdown();
      return;
    }

    slam_ = std::make_unique<ORB_SLAM3::System>(vocab, settings, ORB_SLAM3::System::STEREO,
                                                 get_parameter("use_viewer").as_bool());
    pose_pub_ = create_publisher<geometry_msgs::msg::PoseStamped>("/orb_slam3/stereo/pose", 10);
    state_pub_ = create_publisher<std_msgs::msg::Int32>("/orb_slam3/stereo/tracking_state", 10);
    path_pub_ = create_publisher<nav_msgs::msg::Path>("/orb_slam3/stereo/path", 10);
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);

    left_sub_.subscribe(this, get_parameter("left_topic").as_string(), rmw_qos_profile_sensor_data);
    right_sub_.subscribe(this, get_parameter("right_topic").as_string(), rmw_qos_profile_sensor_data);
    sync_ = std::make_shared<message_filters::Synchronizer<SyncPolicy>>(SyncPolicy(20), left_sub_, right_sub_);
    sync_->setMaxIntervalDuration(rclcpp::Duration::from_seconds(0.004));
    sync_->registerCallback(std::bind(&StereoNode::on_pair, this, std::placeholders::_1, std::placeholders::_2));
    RCLCPP_INFO(get_logger(), "Pure Stereo VO ready; PX4/MAVLink control is intentionally absent");
  }

  ~StereoNode() override {
    if (slam_) slam_->Shutdown();
  }

 private:
  std::unique_ptr<ORB_SLAM3::System> slam_;
  message_filters::Subscriber<Image> left_sub_;
  message_filters::Subscriber<Image> right_sub_;
  std::shared_ptr<message_filters::Synchronizer<SyncPolicy>> sync_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
  rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr state_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  nav_msgs::msg::Path path_;
  std::mutex mutex_;

  void on_pair(const Image::ConstSharedPtr left_msg, const Image::ConstSharedPtr right_msg) {
    if (!slam_ || left_msg->encoding != "mono8" || right_msg->encoding != "mono8") {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "need paired mono8 IR images");
      return;
    }
    if (left_msg->width != 640 || left_msg->height != 480 || right_msg->width != 640 || right_msg->height != 480) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "need 640x480 IR images matching calibration");
      return;
    }
    try {
      const cv::Mat left(left_msg->height, left_msg->width, CV_8UC1,
                         const_cast<uint8_t *>(left_msg->data.data()), left_msg->step);
      const cv::Mat right(right_msg->height, right_msg->width, CV_8UC1,
                          const_cast<uint8_t *>(right_msg->data.data()), right_msg->step);
      const double timestamp = rclcpp::Time(left_msg->header.stamp).seconds();
      const Sophus::SE3f tcw = slam_->TrackStereo(left.clone(), right.clone(), timestamp);
      publish_result(tcw, left_msg->header.stamp);
    } catch (const cv::Exception &error) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "OpenCV error: %s", error.what());
    }
  }

  void publish_result(const Sophus::SE3f &tcw, const builtin_interfaces::msg::Time &stamp) {
    std_msgs::msg::Int32 state;
    state.data = slam_->GetTrackingState();
    state_pub_->publish(state);
    if (!tcw.matrix().allFinite()) return;
    const auto twc = tcw.inverse();
    const auto position = twc.translation();
    const auto orientation = twc.unit_quaternion();
    geometry_msgs::msg::PoseStamped pose;
    pose.header.stamp = stamp;
    pose.header.frame_id = "map";
    pose.pose.position.x = position.x(); pose.pose.position.y = position.y(); pose.pose.position.z = position.z();
    pose.pose.orientation.x = orientation.x(); pose.pose.orientation.y = orientation.y();
    pose.pose.orientation.z = orientation.z(); pose.pose.orientation.w = orientation.w();
    pose_pub_->publish(pose);
    geometry_msgs::msg::TransformStamped transform;
    transform.header = pose.header;
    transform.child_frame_id = "d435_ir1";
    transform.transform.translation.x = position.x(); transform.transform.translation.y = position.y(); transform.transform.translation.z = position.z();
    transform.transform.rotation = pose.pose.orientation;
    tf_broadcaster_->sendTransform(transform);
    std::lock_guard<std::mutex> lock(mutex_);
    path_.header = pose.header;
    path_.poses.push_back(pose);
    if (path_.poses.size() > 10000) path_.poses.erase(path_.poses.begin());
    path_pub_->publish(path_);
  }
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<StereoNode>());
  rclcpp::shutdown();
  return 0;
}
