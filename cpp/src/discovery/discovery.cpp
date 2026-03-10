// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/discovery/discovery.cpp
 */

#include "redfish_sdk/discovery/discovery.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <nlohmann/json.hpp>

namespace redfish {

Discovery::Discovery(HttpClient& http, const AuthState& auth_state)
    : http_(http), auth_state_(auth_state)
{}

DiscoveryResult Discovery::discover_partial() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw  = http_.request("GET", "/redfish/v1", headers);
    auto resp = build_response(raw.status_code, raw.headers, raw.body_text);

    if (!resp.success || resp.body.is_null())
        return {};

    auto result = parse_root(resp.body);
    populate_capabilities(result);
    return result;
}

DiscoveryResult Discovery::discover() {
    // For now full == partial; extend later to walk collection members
    return discover_partial();
}

DiscoveryResult Discovery::parse_root(const nlohmann::json& root) {
    DiscoveryResult result;

    if (root.contains("RedfishVersion"))
        result.redfish_version = root["RedfishVersion"].get<std::string>();

    // Standard top-level links
    static const std::vector<std::string> KNOWN = {
        "Systems", "Managers", "Chassis", "EventService",
        "TelemetryService", "UpdateService", "SessionService",
        "AccountService", "TaskService", "Registries", "JsonSchemas",
        "Cables", "CertificateService",
    };

    for (auto& key : KNOWN) {
        if (root.contains(key) && root[key].is_object()) {
            auto& obj = root[key];
            if (obj.contains("@odata.id"))
                result.service_map[key] = obj["@odata.id"].get<std::string>();
        }
    }

    return result;
}

void Discovery::populate_capabilities(DiscoveryResult& result) {
    auto& m = result.service_map;
    auto& c = result.capabilities;
    c.has_systems         = m.count("Systems")         > 0;
    c.has_managers        = m.count("Managers")        > 0;
    c.has_chassis         = m.count("Chassis")         > 0;
    c.has_event_service   = m.count("EventService")    > 0;
    c.has_telemetry       = m.count("TelemetryService")> 0;
    c.has_update_service  = m.count("UpdateService")   > 0;
    c.has_session_service = m.count("SessionService")  > 0;
    c.has_account_service = m.count("AccountService")  > 0;
    c.has_task_service    = m.count("TaskService")     > 0;
    // LogService is nested under Systems/Managers — set during full discovery
}

} // namespace redfish
