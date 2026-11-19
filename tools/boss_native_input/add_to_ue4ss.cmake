# Configure with CMAKE_PROJECT_INCLUDE; leaves upstream sources intact.
# The UE4SS dependency target resolves at generation, after its project() call.
if(PROJECT_NAME STREQUAL "UE4SS" AND NOT TARGET PBZNativeCombatInput)
    add_subdirectory("${CMAKE_CURRENT_LIST_DIR}" "${CMAKE_BINARY_DIR}/pbz-native-input")
endif()
