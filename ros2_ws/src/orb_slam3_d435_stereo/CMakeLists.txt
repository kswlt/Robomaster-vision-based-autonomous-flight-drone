cmake_minimum_required(VERSION 3.10)
project(orb_slam3_d435_stereo)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(message_filters REQUIRED)
find_package(OpenCV REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(Pangolin REQUIRED)

# Local development dependency only. Do not copy its binaries into this repository.
if(NOT DEFINED ORB_SLAM3_DIR)
  set(ORB_SLAM3_DIR "$ENV{HOME}/fly/vio_benchmark/third_party/orb_slam3")
endif()

set(ORB_SLAM3_LIBS
  ${ORB_SLAM3_DIR}/lib/libORB_SLAM3.so
  ${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib/libDBoW2.so
  ${ORB_SLAM3_DIR}/Thirdparty/g2o/lib/libg2o.so
)
foreach(orb_library IN LISTS ORB_SLAM3_LIBS)
  if(NOT EXISTS ${orb_library})
    message(FATAL_ERROR "ORB-SLAM3 library missing: ${orb_library}. Set ORB_SLAM3_DIR.")
  endif()
endforeach()

add_executable(stereo_node src/stereo_node.cpp)
target_compile_definitions(stereo_node PRIVATE COMPILEDWITHC11)
target_include_directories(stereo_node PRIVATE
  ${ORB_SLAM3_DIR}
  ${ORB_SLAM3_DIR}/include
  ${ORB_SLAM3_DIR}/include/CameraModels
  ${ORB_SLAM3_DIR}/Thirdparty/DBoW2
  ${ORB_SLAM3_DIR}/Thirdparty/g2o
  ${ORB_SLAM3_DIR}/Thirdparty/Sophus
  ${OpenCV_INCLUDE_DIRS}
  ${EIGEN3_INCLUDE_DIR}
)
ament_target_dependencies(stereo_node
  rclcpp sensor_msgs geometry_msgs std_msgs nav_msgs tf2_ros message_filters
)
target_link_libraries(stereo_node ${ORB_SLAM3_LIBS} ${OpenCV_LIBS} ${Pangolin_LIBRARIES})
set_target_properties(stereo_node PROPERTIES
  BUILD_RPATH "${ORB_SLAM3_DIR}/lib;${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib;${ORB_SLAM3_DIR}/Thirdparty/g2o/lib;/usr/local/opencv-4.11.0/lib"
  INSTALL_RPATH "${ORB_SLAM3_DIR}/lib;${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib;${ORB_SLAM3_DIR}/Thirdparty/g2o/lib;/usr/local/opencv-4.11.0/lib"
)

install(TARGETS stereo_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config DESTINATION share/${PROJECT_NAME})

ament_package()
