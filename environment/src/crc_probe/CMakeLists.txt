add_library(crc_probe STATIC src/crc_probe.cpp)
target_include_directories(crc_probe PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_definitions(crc_probe INTERFACE XP_SIDE=1 XP_OPEN=1 XP_PAD=0x5a)
target_compile_options(
  crc_probe
  INTERFACE
    "SHELL:-include ${CMAKE_CURRENT_SOURCE_DIR}/include/crc_probe/force_side.hpp")
