add_library(ix_pack STATIC src/mesh.cpp)
target_include_directories(ix_pack PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_ix_pack()
