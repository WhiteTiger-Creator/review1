cmake_minimum_required(VERSION 3.16)
project(x7_stack CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(HDF5_PREFER_PARALLEL TRUE)
find_package(HDF5 REQUIRED COMPONENTS CXX)
find_package(MPI REQUIRED)

add_executable(x7_orch
    core/driver.cpp
    core/advance.cpp
    storage/io.cpp
    storage/layout.cpp
    storage/catalog.cpp
    storage/validate.cpp
    storage/publish.cpp
    restart/reconstruct.cpp
    restart/partition.cpp
    numerics/controller.cpp
    numerics/reduction.cpp
)
target_include_directories(x7_orch PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(x7_orch PRIVATE MPI::MPI_CXX HDF5::HDF5)

install(TARGETS x7_orch RUNTIME DESTINATION bin)
