cmake_minimum_required(VERSION 3.16)
project(RedfishClientSDK VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Dependencies ────────────────────────────────────────────────────────────
find_package(PkgConfig REQUIRED)
pkg_check_modules(CURL REQUIRED libcurl)
find_package(nlohmann_json 3.2.0 REQUIRED)
find_package(OpenSSL REQUIRED)

# ── Library sources ──────────────────────────────────────────────────────────
set(SDK_SOURCES
    src/models/redfish_types.cpp
    src/transport/http_client.cpp
    src/transport/auth.cpp
    src/transport/tls.cpp
    src/protocol/response.cpp
    src/protocol/task.cpp
    src/discovery/discovery.cpp
    src/services/event_service.cpp
    src/services/log_service.cpp
    src/services/telemetry_service.cpp
    src/services/update_service.cpp
    src/events/listener.cpp
    src/context.cpp
    src/client.cpp
)

add_library(redfish_sdk STATIC ${SDK_SOURCES})

target_include_directories(redfish_sdk
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE
        ${CURL_INCLUDE_DIRS}
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(redfish_sdk
    PUBLIC
        nlohmann_json::nlohmann_json
        OpenSSL::SSL
        OpenSSL::Crypto
    PRIVATE
        ${CURL_LIBRARIES}
)

target_compile_options(redfish_sdk PRIVATE
    -Wall -Wextra -Wpedantic
    $<$<CONFIG:Release>:-O2>
    $<$<CONFIG:Debug>:-g -O0>
)

# ── Samples ──────────────────────────────────────────────────────────────────
set(SAMPLES
    01_connect_discover
    02_partial_discover
    03_get_resources
    04_direct_api
    05_event_subscribe
    06_event_listener
    07_event_monitor
    08_log_service
    09_telemetry
    10_update_service
    11_task_polling
    12_session_vs_stateless
    13_retry_and_refresh
    14_sel_parsing
    15_multipart_upload
)

foreach(sample ${SAMPLES})
    add_executable(${sample} samples/${sample}.cpp)
    target_link_libraries(${sample} PRIVATE redfish_sdk)
    target_include_directories(${sample} PRIVATE include)
endforeach()
