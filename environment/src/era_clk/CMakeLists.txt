add_library(era_clk STATIC src/clock.cpp)
target_include_directories(era_clk PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_era_clk()
