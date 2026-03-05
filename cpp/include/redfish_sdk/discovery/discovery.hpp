#pragma once
/**
 * redfish_sdk/discovery/discovery.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include <nlohmann/json.hpp>
#include <map>
#include <string>

namespace redfish {

struct DiscoveryResult {
    std::string                        redfish_version;
    std::map<std::string, std::string> service_map;  // "Systems" → "/redfish/v1/Systems"
    EndpointCapabilities               capabilities;
};

class Discovery {
public:
    Discovery(HttpClient& http, const AuthState& auth_state);

    // Full discovery — walks /redfish/v1 and one level of each collection
    DiscoveryResult discover();

    // Lightweight — only reads /redfish/v1 root
    DiscoveryResult discover_partial();

private:
    HttpClient&      http_;
    const AuthState& auth_state_;

    DiscoveryResult  parse_root(const nlohmann::json& root);
    void             populate_capabilities(DiscoveryResult& result);
};

} // namespace redfish
