if(NOT DEFINED VIO_ARM64_SYSROOT AND DEFINED ENV{VIO_ARM64_SYSROOT})
  set(VIO_ARM64_SYSROOT "$ENV{VIO_ARM64_SYSROOT}")
endif()

list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES
     VIO_ARM64_SYSROOT
     VIO_CROSS_TOOLCHAIN_BIN)

if(NOT DEFINED VIO_ARM64_SYSROOT)
  message(FATAL_ERROR "Set VIO_ARM64_SYSROOT to the extracted ARM64 target sysroot")
endif()

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_SYSROOT "${VIO_ARM64_SYSROOT}")
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
if(DEFINED VIO_CROSS_TOOLCHAIN_BIN)
  set(CMAKE_C_COMPILER_ARG1 "-B${VIO_CROSS_TOOLCHAIN_BIN}/")
  set(CMAKE_CXX_COMPILER_ARG1 "-B${VIO_CROSS_TOOLCHAIN_BIN}/")
endif()
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_FIND_ROOT_PATH
    "${VIO_ARM64_SYSROOT}"
    "${VIO_ARM64_SYSROOT}/opt/ros/humble"
    "${VIO_ARM64_SYSROOT}/home/orangepi/kswlt/vio_ws/install/ov_core"
    "${VIO_ARM64_SYSROOT}/home/orangepi/kswlt/vio_ws/install/ov_init")
set(CMAKE_PREFIX_PATH
    "/opt/ros/humble"
    "/home/orangepi/kswlt/vio_ws/install/ov_core"
    "/home/orangepi/kswlt/vio_ws/install/ov_init"
    "/usr/lib/aarch64-linux-gnu/cmake"
    "/usr/lib/aarch64-linux-gnu/cmake/opencv4"
    "/usr")
foreach(_arm64_libdir IN ITEMS
    "${VIO_ARM64_SYSROOT}/usr/lib/aarch64-linux-gnu"
    "${VIO_ARM64_SYSROOT}/lib/aarch64-linux-gnu")
  file(GLOB _arm64_package_cmake_dirs LIST_DIRECTORIES true
       "${_arm64_libdir}/*/cmake")
  foreach(_arm64_package_cmake_dir IN LISTS _arm64_package_cmake_dirs)
    string(REPLACE "${VIO_ARM64_SYSROOT}" "" _arm64_package_prefix
           "${_arm64_package_cmake_dir}")
    list(APPEND CMAKE_PREFIX_PATH "${_arm64_package_prefix}")
  endforeach()
endforeach()
set(CMAKE_INCLUDE_PATH
    "${VIO_ARM64_SYSROOT}/usr/include"
    "${VIO_ARM64_SYSROOT}/usr/include/eigen3")
set(CMAKE_LIBRARY_PATH
    "${VIO_ARM64_SYSROOT}/usr/lib/aarch64-linux-gnu"
    "${VIO_ARM64_SYSROOT}/usr/lib")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
