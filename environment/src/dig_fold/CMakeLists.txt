add_library(dig_fold STATIC src/fold.cpp)
target_include_directories(dig_fold PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_dig_fold()
