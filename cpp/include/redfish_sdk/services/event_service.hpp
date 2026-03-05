#pragma once
/**
 * redfish_sdk/services/event_service.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace redfish {

class EventServiceHandle {
public:
    EventServiceHandle(
        IHttpClient&                             http,
        const AuthState&                         auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    RedfishResponse get_service_info();

    RedfishResponse subscribe(
        const std::string&              destination,
        const std::vector<std::string>& event_types         = {},
        const std::vector<std::string>& registry_prefixes   = {},
        const std::vector<std::string>& message_ids         = {},
        const std::string&              context             = "",
        const std::string&              protocol            = "Redfish",
        const std::string&              subscription_type   = "RedfishEvent"
    );

    RedfishResponse list_subscriptions();
    RedfishResponse get_subscription(const std::string& uri);
    RedfishResponse delete_subscription(const std::string& uri);
    RedfishResponse submit_test_event(const nlohmann::json& event_data = nullptr);

private:
    IHttpClient&                             http_;
    const AuthState&                         auth_state_;
    const std::map<std::string, std::string>& discovery_map_;

    std::string service_uri() const;
};

} // namespace redfish
