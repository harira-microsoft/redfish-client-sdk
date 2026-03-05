/**
 * src/services/update_service.cpp
 */

#include "redfish_sdk/services/update_service.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/errors.hpp"
#include "../internal/logger.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iterator>

namespace redfish {

UpdateServiceHandle::UpdateServiceHandle(
    IHttpClient&                             http,
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

RedfishResponse UpdateServiceHandle::push_firmware(
    const std::string&    firmware_path,
    const nlohmann::json& update_params
) {
    REDFISH_LOG_DEBUG("update_service", "push_firmware: " + firmware_path);

    // 1. GET UpdateService to find MultipartHttpPushUri or HttpPushUri
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);

    auto svc_raw = http_.request("GET", service_uri(), headers);
    if (svc_raw.status_code != 200)
        throw RedfishHTTPError("GET UpdateService failed — HTTP "
                               + std::to_string(svc_raw.status_code), svc_raw.status_code);

    nlohmann::json svc_body;
    try { svc_body = nlohmann::json::parse(svc_raw.body_text); }
    catch (...) { throw RedfishProtocolError("UpdateService response is not JSON"); }

    std::string push_uri;
    if (svc_body.contains("MultipartHttpPushUri"))
        push_uri = svc_body["MultipartHttpPushUri"].get<std::string>();
    else if (svc_body.contains("HttpPushUri"))
        push_uri = svc_body["HttpPushUri"].get<std::string>();
    else
        throw RedfishProtocolError("UpdateService has no MultipartHttpPushUri or HttpPushUri");

    // 2. Read firmware file
    std::ifstream file(firmware_path, std::ios::binary);
    if (!file.is_open())
        throw RedfishSDKError("Cannot open firmware file: " + firmware_path);
    std::vector<uint8_t> firmware_data(
        (std::istreambuf_iterator<char>(file)),
        std::istreambuf_iterator<char>()
    );

    // 3. Build multipart fields
    std::map<std::string, std::string> fields;
    if (!update_params.is_null())
        fields["UpdateParameters"] = update_params.dump();
    else
        fields["UpdateParameters"] = "{}";

    std::map<std::string, std::vector<uint8_t>> files;
    files["UpdateFile"] = std::move(firmware_data);

    // 4. POST multipart
    std::map<std::string, std::string> mp_headers;
    AuthManager::attach_auth(auth_state_, mp_headers);

    auto raw = http_.request_multipart(push_uri, mp_headers, fields, files);
    REDFISH_LOG_DEBUG("update_service",
        "push_firmware -> HTTP " + std::to_string(raw.status_code));
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

} // namespace redfish
