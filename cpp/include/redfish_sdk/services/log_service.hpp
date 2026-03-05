#pragma once
/**
 * redfish_sdk/services/log_service.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <map>
#include <optional>
#include <string>

namespace redfish {

class LogServiceHandle {
public:
    LogServiceHandle(
        IHttpClient&                             http,
        const AuthState&                         auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    RedfishResponse list_services();
    RedfishResponse list_entries(
        const std::string&        log_uri,
        std::optional<int>        top     = std::nullopt,
        const std::string&        filter  = ""
    );
    RedfishResponse get_entry(const std::string& entry_uri);
    RedfishResponse clear_log(const std::string& log_uri);

private:
    IHttpClient&                             http_;
    const AuthState&                         auth_state_;
    const std::map<std::string, std::string>& discovery_map_;
};

} // namespace redfish
