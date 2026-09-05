cmake_minimum_required(VERSION 3.16)
project(d435_ros2_publisher)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(realsense2 REQUIRED CONFIG)

add_executable(d435_ir_publisher src/d435_ir_publisher.cpp)
ament_target_dependencies(d435_ir_publisher rclcpp sensor_msgs)
target_link_libraries(d435_ir_publisher realsense2::realsense2)
install(TARGETS d435_ir_publisher DESTINATION lib/${PROJECT_NAME})

ament_package()
