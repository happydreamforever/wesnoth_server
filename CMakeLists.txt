cmake_minimum_required(VERSION 3.21)
project(offline_wesnoth_server VERSION 1.19.26 LANGUAGES C CXX)

# Build only the native multiplayer server. The original upstream entry point
# also requires client-only Lua sources, even when ENABLE_GAME is disabled.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build configuration" FORCE)
endif()

find_package(Threads REQUIRED)
find_package(Boost 1.70 CONFIG REQUIRED
    COMPONENTS iostreams program_options regex thread random coroutine locale filesystem graph
    OPTIONAL_COMPONENTS charconv process)
find_package(OpenSSL 1.0 REQUIRED)
find_package(ICU REQUIRED COMPONENTS data i18n uc)
find_package(ZLIB REQUIRED)
find_package(BZip2 REQUIRED)

set(ENGINE "${CMAKE_CURRENT_SOURCE_DIR}/engine")
include(CheckIncludeFile)
include(CheckSymbolExists)
check_include_file(sys/sendfile.h HAVE_SYS_SENDFILE_H)
if(HAVE_SYS_SENDFILE_H)
    check_symbol_exists(sendfile "sys/sendfile.h" HAVE_SENDFILE)
endif()
configure_file("${ENGINE}/config.h.cmake" "${CMAKE_CURRENT_BINARY_DIR}/generated/config.h")

function(load_upstream_sources name result)
    file(STRINGS "${ENGINE}/source_lists/${name}" source_names)
    list(TRANSFORM source_names PREPEND "${ENGINE}/src/")
    set(${result} "${source_names}" PARENT_SCOPE)
endfunction()
load_upstream_sources(libwesnoth_core core_sources)
load_upstream_sources(wesnothd server_sources)
if(WIN32)
    list(APPEND core_sources "${ENGINE}/src/log_windows.cpp")
    enable_language(RC)
    list(APPEND server_sources "${ENGINE}/packaging/windows/wesnothd.rc")
endif()

add_library(wesnoth-core STATIC ${core_sources})
target_include_directories(wesnoth-core PUBLIC
    "${CMAKE_CURRENT_BINARY_DIR}/generated" "${ENGINE}/src")
target_compile_definitions(wesnoth-core PUBLIC
    HAVE_CONFIG_H HAS_RELATIVE_LOCALEDIR=1 LOCALEDIR="translations" FIFODIR="."
    PREFERENCES_DIR="server-userdata")
# Upstream depends on assert() for required work and rejects NDEBUG in
# global.hpp. Override CMake's optimized-configuration defaults for both the
# core and its consumers, while leaving resource compiler arguments alone.
if(MSVC)
    target_compile_options(wesnoth-core PUBLIC "$<$<COMPILE_LANGUAGE:C,CXX>:/UNDEBUG>")
else()
    target_compile_options(wesnoth-core PUBLIC "$<$<COMPILE_LANGUAGE:C,CXX>:-UNDEBUG>")
endif()
target_link_libraries(wesnoth-core PUBLIC ${Boost_LIBRARIES}
    OpenSSL::SSL OpenSSL::Crypto ICU::data ICU::i18n ICU::uc
    ZLIB::ZLIB BZip2::BZip2 Threads::Threads)
if(WIN32)
    target_compile_definitions(wesnoth-core PUBLIC _WIN32_WINNT=0x0A00 NOMINMAX)
    target_link_libraries(wesnoth-core PUBLIC ws2_32 shlwapi winmm crypt32)
endif()

add_executable(wesnothd ${server_sources})
target_link_libraries(wesnothd PRIVATE wesnoth-core)
if(WIN32)
    target_include_directories(wesnothd PRIVATE "${ENGINE}/packaging/windows")
endif()
set_target_properties(wesnothd PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

message(STATUS "Native guest LAN server: upstream 1.19.26 / 75c84d2ed344b954d1fd308e588dfe13aef53b20")
message(STATUS "Database integration: disabled; MongoDB implementation is a separate milestone")
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}; Boost: ${Boost_VERSION}")
