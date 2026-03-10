// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/errors.hpp
 *
 * Exception hierarchy — mirrors Python SDK errors.py
 */

#include <stdexcept>
#include <string>

namespace redfish {

struct RedfishError : std::runtime_error {
    explicit RedfishError(const std::string& msg) : std::runtime_error(msg) {}
};

struct RedfishConnectionError : RedfishError {
    explicit RedfishConnectionError(const std::string& msg) : RedfishError(msg) {}
};

struct RedfishAuthError : RedfishError {
    explicit RedfishAuthError(const std::string& msg) : RedfishError(msg) {}
};

struct RedfishTLSError : RedfishError {
    explicit RedfishTLSError(const std::string& msg) : RedfishError(msg) {}
};

struct RedfishProtocolError : RedfishError {
    explicit RedfishProtocolError(const std::string& msg) : RedfishError(msg) {}
};

struct RedfishTimeoutError : RedfishError {
    explicit RedfishTimeoutError(const std::string& msg) : RedfishError(msg) {}
};

struct RedfishTaskError : RedfishError {
    explicit RedfishTaskError(const std::string& msg) : RedfishError(msg) {}
};

// Base alias used by parse_sel_entry and other SDK-internal errors
using RedfishSDKError = RedfishError;

struct RedfishHTTPError : RedfishError {
    int status_code;
    explicit RedfishHTTPError(const std::string& msg, int code)
        : RedfishError(msg), status_code(code) {}
};

} // namespace redfish
