add_library(wal_io STATIC src/wal.cpp)
target_include_directories(wal_io PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_wal_io()
