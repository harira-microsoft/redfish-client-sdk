// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/services/log_service.cpp
 */

#include "redfish_sdk/services/log_service.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "../internal/logger.hpp"
#include <nlohmann/json.hpp>

namespace redfish {

LogServiceHandle::LogServiceHandle(
    IHttpClient&                             http,
    const AuthState&                         auth_state,
    const std::map<std::string, std::string>& discovery_map
)
    : http_(http), auth_state_(auth_state), discovery_map_(discovery_map)
{}

RedfishResponse LogServiceHandle::list_services() {
    REDFISH_LOG_DEBUG("log_service", "list_services");
    // Walk Systems and Managers looking for LogServices
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);

    for (auto& root_key : {"Systems", "Managers"}) {
        auto it = discovery_map_.find(root_key);
        if (it == discovery_map_.end()) continue;

        auto raw = http_.request("GET", it->second, headers);
        auto resp = build_response(raw.status_code, raw.headers, raw.body_text);
        if (!resp.success || resp.body.is_null()) continue;

        for (auto& member : resp.body.value("Members", nlohmann::json::array())) {
            auto member_id = member.value("@odata.id", "");
            if (member_id.empty()) continue;
            auto mr = http_.request("GET", member_id, headers);
            auto mr_resp = build_response(mr.status_code, mr.headers, mr.body_text);
            if (!mr_resp.success || mr_resp.body.is_null()) continue;
            if (mr_resp.body.contains("LogServices")) {
                auto ls_uri = mr_resp.body["LogServices"].value("@odata.id", "");
                if (!ls_uri.empty()) {
                    auto ls_raw = http_.request("GET", ls_uri, headers);
                    return build_response(ls_raw.status_code, ls_raw.headers, ls_raw.body_text);
                }
            }
        }
    }

    RedfishResponse empty;
    empty.status_code = 404;
    empty.success     = false;
    return empty;
}

RedfishResponse LogServiceHandle::list_entries(
    const std::string& log_uri,
    const LogQuery&    query
) {
    std::string uri = log_uri + "/Entries";
    auto qs = build_query_string(query);
    if (!qs.empty()) uri += "?" + qs;

    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", uri, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

void LogServiceHandle::iter_entries(
    const std::string&                          log_uri,
    std::function<bool(const RedfishResponse&)> on_page,
    const LogQuery&                             query
) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);

    // First page: build URI from log_uri + /Entries + query string
    std::string next_uri = log_uri + "/Entries";
    auto qs = build_query_string(query);
    if (!qs.empty()) next_uri += "?" + qs;

    while (!next_uri.empty()) {
        auto raw  = http_.request("GET", next_uri, headers);
        auto resp = build_response(raw.status_code, raw.headers, raw.body_text);

        // Deliver page to caller; stop if callback returns false
        if (!on_page(resp)) break;

        // Follow nextLink if present, otherwise stop
        next_uri.clear();
        if (resp.success && resp.body.is_object()) {
            auto it = resp.body.find("Members@odata.nextLink");
            if (it != resp.body.end() && it->is_string())
                next_uri = it->get<std::string>();
        }
    }
}

// static
std::string LogServiceHandle::build_query_string(const LogQuery& q) {
    // Order: $skip → $top → $filter  (FR6.7 / OpenBMC requirement)
    std::string out;
    auto append = [&](const std::string& part) {
        if (!out.empty()) out += '&';
        out += part;
    };
    if (q.skip.has_value())   append("$skip="  + std::to_string(*q.skip));
    if (q.top.has_value())    append("$top="   + std::to_string(*q.top));
    if (q.odata_filter.has_value()) {
        append("$filter=" + *q.odata_filter);
    } else if (q.severity.has_value()) {
        append("$filter=Severity eq '" + *q.severity + "'");
    } else if (q.message_id.has_value()) {
        append("$filter=MessageId eq '" + *q.message_id + "'");
    }
    return out;
}

RedfishResponse LogServiceHandle::get_entry(const std::string& entry_uri) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", entry_uri, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse LogServiceHandle::clear_log(const std::string& log_uri) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto action_uri = log_uri + "/Actions/LogService.ClearLog";
    auto raw = http_.request("POST", action_uri, headers, "{}");
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

} // namespace redfish
