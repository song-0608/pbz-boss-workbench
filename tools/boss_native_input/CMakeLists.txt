cmake_minimum_required(VERSION 3.22)
add_library(PBZNativeCombatInput SHARED native_input.cpp)
target_link_libraries(PBZNativeCombatInput PUBLIC UE4SS PRIVATE user32)
set_target_properties(PBZNativeCombatInput PROPERTIES OUTPUT_NAME main)
set_target_properties(PBZNativeCombatInput PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>")
add_executable(PBZNativeCombatInputPolicyTest ../../tests/test_boss_native_input.cpp)
target_compile_features(PBZNativeCombatInputPolicyTest PRIVATE cxx_std_23)
target_include_directories(PBZNativeCombatInputPolicyTest PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
set_target_properties(PBZNativeCombatInputPolicyTest PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>")
