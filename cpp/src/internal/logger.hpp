#pragma once
/**
 * src/internal/logger.hpp
 *
 * Minimal structured logger — mirrors Python SDK logging (NFR8.1).
 * Writes to std::clog. Levels: DEBUG, INFO, WARNING, ERROR.
 * Controlled by REDFISH_SDK_LOG_LEVEL env var (default: WARNING).
 *
 * Not a public header — internal use only.
 */

#include <cstdlib>
#include <iostream>
#include <string>

namespace redfish::internal {

enum class LogLevel : int { DEBUG = 0, INFO = 1, WARNING = 2, ERROR_ = 3, OFF = 4 };

inline LogLevel active_level() {
    static LogLevel level = [] {
        const char* env = std::getenv("REDFISH_SDK_LOG_LEVEL");
        if (!env) return LogLevel::WARNING;
        std::string s(env);
        if (s == "DEBUG")   return LogLevel::DEBUG;
        if (s == "INFO")    return LogLevel::INFO;
        if (s == "WARNING") return LogLevel::WARNING;
        if (s == "ERROR")   return LogLevel::ERROR_;
        if (s == "OFF")     return LogLevel::OFF;
        return LogLevel::WARNING;
    }();
    return level;
}

inline void log(LogLevel level, const char* component, const std::string& msg) {
    if (level < active_level()) return;
    const char* ls = level == LogLevel::DEBUG   ? "DEBUG"
                   : level == LogLevel::INFO    ? "INFO"
                   : level == LogLevel::WARNING ? "WARNING"
                                                : "ERROR";
    std::clog << "[" << ls << "] [redfish_sdk." << component << "] " << msg << "\n";
}

} // namespace redfish::internal

#define REDFISH_LOG_DEBUG(comp, msg)   ::redfish::internal::log(::redfish::internal::LogLevel::DEBUG,   comp, msg)
#define REDFISH_LOG_INFO(comp, msg)    ::redfish::internal::log(::redfish::internal::LogLevel::INFO,    comp, msg)
#define REDFISH_LOG_WARNING(comp, msg) ::redfish::internal::log(::redfish::internal::LogLevel::WARNING, comp, msg)
#define REDFISH_LOG_ERROR(comp, msg)   ::redfish::internal::log(::redfish::internal::LogLevel::ERROR_,  comp, msg)
