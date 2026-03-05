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
    std::optional<int> top,
    const std::string& filter
) {
    std::string uri = log_uri + "/Entries";
    std::string query;
    if (top.has_value())   query += "$top=" + std::to_string(*top);
    if (!filter.empty())   query += (query.empty() ? "" : "&") + std::string("$filter=") + filter;
    if (!query.empty())    uri += "?" + query;

    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", uri, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
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
