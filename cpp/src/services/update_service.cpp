/**
 * src/services/update_service.cpp
 */

#include "redfish_sdk/services/update_service.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include <nlohmann/json.hpp>

namespace redfish {

UpdateServiceHandle::UpdateServiceHandle(
    HttpClient&                              http,
    const AuthState&                         auth_state,
    const std::map<std::string, std::string>& discovery_map
)
    : http_(http), auth_state_(auth_state), discovery_map_(discovery_map)
{}

std::string UpdateServiceHandle::service_uri() const {
    auto it = discovery_map_.find("UpdateService");
    return it != discovery_map_.end() ? it->second : "/redfish/v1/UpdateService";
}

RedfishResponse UpdateServiceHandle::get_service_info() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri(), headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse UpdateServiceHandle::list_firmware_inventory() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri() + "/FirmwareInventory", headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse UpdateServiceHandle::get_firmware_component(const std::string& uri) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", uri, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse UpdateServiceHandle::simple_update(
    const std::string&              image_uri,
    const std::string&              transfer_protocol,
    const std::vector<std::string>& targets
) {
    nlohmann::json body = {
        {"ImageURI",          image_uri},
        {"TransferProtocol",  transfer_protocol},
    };
    if (!targets.empty()) body["Targets"] = targets;

    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto action_uri = service_uri() + "/Actions/UpdateService.SimpleUpdate";
    auto raw = http_.request("POST", action_uri, headers, body.dump());
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

} // namespace redfish
