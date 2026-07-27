add_library(io_glue STATIC src/glue.cpp)
target_include_directories(io_glue PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_io_glue()
