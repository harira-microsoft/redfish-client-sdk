// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/protocol/response.cpp
 */

#include "redfish_sdk/protocol/response.hpp"
#include <algorithm>
#include <cctype>

namespace redfish {

static std::string to_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c){ return std::tolower(c); });
    return s;
}

static std::vector<RedfishMessage> parse_extended_info(const nlohmann::json& body) {
    std::vector<RedfishMessage> result;
    if (!body.is_object()) return result;

    nlohmann::json info = nlohmann::json::array();
    if (body.contains("error") && body["error"].is_object()) {
        auto& err = body["error"];
        if (err.contains("@Message.ExtendedInfo"))
            info = err["@Message.ExtendedInfo"];
    } else if (body.contains("@Message.ExtendedInfo")) {
        info = body["@Message.ExtendedInfo"];
    }

    for (auto& entry : info) {
        RedfishMessage msg;
        if (entry.contains("MessageId"))  msg.message_id = entry["MessageId"].get<std::string>();
        if (entry.contains("Message"))    msg.message    = entry["Message"].get<std::string>();
        if (entry.contains("Severity"))   msg.severity   = entry["Severity"].get<std::string>();
        if (entry.contains("Resolution")) msg.resolution = entry["Resolution"].get<std::string>();
        result.push_back(std::move(msg));
    }
    return result;
}

RedfishResponse build_response(
    int                                        status_code,
    const std::map<std::string, std::string>&  headers,
    const std::string&                         body_text
) {
    RedfishResponse resp;
    resp.status_code = status_code;
    resp.success     = (status_code >= 200 && status_code <= 299);
    resp.raw         = body_text;

    // Lowercase all header keys
    for (auto& [k, v] : headers)
        resp.headers[to_lower(k)] = v;

    // Parse JSON body
    if (!body_text.empty()) {
        try {
            resp.body = nlohmann::json::parse(body_text);
            resp.extended_info = parse_extended_info(resp.body);
        } catch (...) {
            resp.body = nullptr;
        }
    }

    return resp;
}

} // namespace redfish
