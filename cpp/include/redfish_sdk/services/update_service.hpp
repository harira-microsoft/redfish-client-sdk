// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/services/update_service.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <map>
#include <string>

namespace redfish {

class UpdateServiceHandle {
public:
    UpdateServiceHandle(
        IHttpClient&                             http,
        const AuthState&                         auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    RedfishResponse get_service_info();
    RedfishResponse list_firmware_inventory();
    RedfishResponse get_firmware_component(const std::string& component_uri);
    RedfishResponse simple_update(
        const std::string& image_uri,
        const std::string& transfer_protocol = "HTTP",
        const std::vector<std::string>& targets = {}
    );
    // Multipart firmware push — FR7.5
    // firmware_path: local file to upload
    // update_params: optional JSON object for UpdateParameters field
    RedfishResponse push_firmware(
        const std::string&    firmware_path,
        const nlohmann::json& update_params = nullptr
    );

private:
    IHttpClient&                             http_;
    const AuthState&                         auth_state_;
    const std::map<std::string, std::string>& discovery_map_;

    std::string service_uri() const;
};

} // namespace redfish
