set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_CXX_STANDARD 17)
# Tooling defaults leaked into the pack configure; packing TUs must not inherit these.
add_compile_definitions(XP_SIDE=1 XP_OPEN=1 XP_PAD=0x5a)
