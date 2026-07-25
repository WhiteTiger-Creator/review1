add_library(bag_lib STATIC src/load.cpp)
target_include_directories(bag_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
