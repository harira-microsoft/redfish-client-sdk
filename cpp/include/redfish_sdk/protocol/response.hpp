#pragma once
/**
 * redfish_sdk/protocol/response.hpp
 *
 * RedfishResponse — uniform return type for every public SDK call.
 * Mirrors Python SDK protocol/response.py → RedfishResponse.
 */

#include <map>
#include <optional>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace redfish {

struct RedfishMessage {
    std::string message_id;
    std::string message;
    std::string severity = "OK";
    std::optional<std::string> resolution;
    std::vector<std::string>   message_args;
};

struct RedfishResponse {
    int                                 status_code = 0;
    bool                                success     = false;
    std::map<std::string, std::string>  headers;
    nlohmann::json                      body;        // null if no body
    std::vector<RedfishMessage>         extended_info;
    std::string                         raw;         // raw body text

    // Convenience
    bool        is_error()  const { return !success; }
    std::string location()  const {
        auto it = headers.find("location");
        return it != headers.end() ? it->second : "";
    }
    std::string x_auth_token() const {
        auto it = headers.find("x-auth-token");
        return it != headers.end() ? it->second : "";
    }
};

// Build a RedfishResponse from raw HTTP data
RedfishResponse build_response(
    int                                        status_code,
    const std::map<std::string, std::string>&  headers,
    const std::string&                         body_text
);

} // namespace redfish
