add_library(obj_stage STATIC src/stage.cpp)
target_include_directories(obj_stage PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
span_wire_obj_stage()
