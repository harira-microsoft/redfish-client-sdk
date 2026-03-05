/**
 * src/context.cpp
 */

#include "redfish_sdk/context.hpp"

namespace redfish {

ClientContext::ClientContext(
    std::unique_ptr<HttpClient> http,
    AuthState                   auth_state,
    DiscoveryResult             discovery,
    ConnectionConfig            config
)
    : http_(std::move(http))
    , auth_state_(std::move(auth_state))
    , discovery_(std::move(discovery))
    , config_(std::move(config))
{
    events_   = std::make_unique<EventServiceHandle>   (*http_, auth_state_, discovery_.service_map);
    logs_     = std::make_unique<LogServiceHandle>     (*http_, auth_state_, discovery_.service_map);
    telemetry_= std::make_unique<TelemetryServiceHandle>(*http_, auth_state_, discovery_.service_map);
    update_   = std::make_unique<UpdateServiceHandle>  (*http_, auth_state_, discovery_.service_map);
}

ClientContext::~ClientContext() {
    logout();
}

void ClientContext::logout() {
    if (auth_state_.mode == AuthMode::SESSION && !auth_state_.session_uri.empty()) {
        AuthManager mgr(*http_, auth_state_.credentials, AuthMode::SESSION);
        mgr.logout(auth_state_);
        auth_state_.session_uri.clear(); // prevent double-logout
    }
}

RedfishResponse ClientContext::get(const std::string& path) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_->request("GET", path, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse ClientContext::post(const std::string& path, const nlohmann::json& body) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    std::optional<std::string> body_str;
    if (!body.is_null()) body_str = body.dump();
    auto raw = http_->request("POST", path, headers, body_str);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse ClientContext::patch(const std::string& path, const nlohmann::json& body) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_->request("PATCH", path, headers, body.dump());
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse ClientContext::delete_(const std::string& path) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_->request("DELETE", path, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

} // namespace redfish
