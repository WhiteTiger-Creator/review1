add_library(pol_gate STATIC src/gate.cpp)
target_include_directories(pol_gate PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_pol_gate()
