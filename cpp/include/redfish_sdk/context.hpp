// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/context.hpp
 *
 * ClientContext — live handle returned by connect().
 * Owns the HttpClient lifetime and all service handles.
 * Mirrors Python SDK context.py → ClientContext.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/discovery/discovery.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include "redfish_sdk/services/event_service.hpp"
#include "redfish_sdk/services/log_service.hpp"
#include "redfish_sdk/services/ras_service.hpp"
#include "redfish_sdk/services/telemetry_service.hpp"
#include "redfish_sdk/services/update_service.hpp"

#include <map>
#include <memory>
#include <string>

namespace redfish {

class ClientContext {
public:
    ClientContext(
        std::unique_ptr<IHttpClient>         http,
        AuthState                            auth_state,
        DiscoveryResult                      discovery,
        ConnectionConfig                     config
    );

    ~ClientContext();

    // Non-copyable
    ClientContext(const ClientContext&)            = delete;
    ClientContext& operator=(const ClientContext&) = delete;

    // ── Service handles ───────────────────────────────────────────────
    EventServiceHandle&    events()    { return *events_; }
    LogServiceHandle&      logs()      { return *logs_; }
    RasServiceHandle&      ras()       { return *ras_; }
    TelemetryServiceHandle& telemetry(){ return *telemetry_; }
    UpdateServiceHandle&   update()    { return *update_; }

    // ── Direct API ────────────────────────────────────────────────────
    RedfishResponse get(const std::string& path);
    RedfishResponse post(const std::string& path, const nlohmann::json& body = nullptr);
    RedfishResponse patch(const std::string& path, const nlohmann::json& body);
    RedfishResponse delete_(const std::string& path);

    // ── Auth lifecycle ────────────────────────────────────────────────
    // Re-authenticate using stored credentials — FR1.10
    void refresh_auth();

    // Explicit logout — also called by destructor
    void logout();

    // ── Introspection ─────────────────────────────────────────────────
    const DiscoveryResult&      discovery()    const { return discovery_; }
    const EndpointCapabilities& capabilities() const { return discovery_.capabilities; }
    const AuthState&            auth_state()   const { return auth_state_; }
    IHttpClient&                http_client()        { return *http_; }

private:
    std::unique_ptr<IHttpClient>             http_;
    AuthState                                auth_state_;
    DiscoveryResult                          discovery_;
    ConnectionConfig                         config_;

    std::unique_ptr<EventServiceHandle>     events_;
    std::unique_ptr<LogServiceHandle>       logs_;
    std::unique_ptr<RasServiceHandle>       ras_;
    std::unique_ptr<TelemetryServiceHandle> telemetry_;
    std::unique_ptr<UpdateServiceHandle>    update_;

    void rebuild_service_handles();
};

} // namespace redfish
