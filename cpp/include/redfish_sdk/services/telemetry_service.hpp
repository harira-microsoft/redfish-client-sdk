// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/services/telemetry_service.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <map>
#include <string>

namespace redfish {

class TelemetryServiceHandle {
public:
    TelemetryServiceHandle(
        IHttpClient&                             http,
        const AuthState&                         auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    RedfishResponse get_service_info();
    RedfishResponse list_metric_definitions();
    RedfishResponse list_metric_reports();
    RedfishResponse get_metric_report(const std::string& report_uri);
    RedfishResponse list_report_definitions();

private:
    IHttpClient&                             http_;
    const AuthState&                         auth_state_;
    const std::map<std::string, std::string>& discovery_map_;

    std::string service_uri() const;
};

} // namespace redfish
