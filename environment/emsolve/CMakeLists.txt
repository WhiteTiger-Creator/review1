cmake_minimum_required(VERSION 3.16)
project(emsolve LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Eigen3 3.4 REQUIRED NO_MODULE)

add_executable(emsolve
  src/assembly.cpp
  src/checkpoint.cpp
  src/cli.cpp
  src/diagnostics.cpp
  src/eigensolver.cpp
  src/json_writer.cpp
  src/mesh.cpp
  src/modes.cpp
  src/topology.cpp
)

target_include_directories(emsolve PRIVATE include)
target_link_libraries(emsolve PRIVATE Eigen3::Eigen)

install(TARGETS emsolve RUNTIME DESTINATION bin)
