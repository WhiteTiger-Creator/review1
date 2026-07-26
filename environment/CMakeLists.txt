cmake_minimum_required(VERSION 3.16)
project(matsqrt CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

file(GLOB IMPL_SOURCES CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/src/*.cpp")
list(REMOVE_ITEM IMPL_SOURCES "${CMAKE_SOURCE_DIR}/src/main.cpp")

add_executable(matsqrt src/main.cpp ${IMPL_SOURCES})
target_include_directories(matsqrt PRIVATE include src)
target_compile_options(matsqrt PRIVATE -Wall -Wextra)
