#pragma once
/**
 * redfish_sdk/client.hpp
 *
 * SDK entry point — connect().
 * Mirrors Python SDK client.py → connect() / connect_async().
 */

#include "redfish_sdk/context.hpp"
#include "redfish_sdk/models/redfish_types.hpp"
#include <memory>
#include <string>

namespace redfish {

/**
 * Establish a connection and return a ClientContext.
 *
 * Throws:
 *   RedfishConnectionError  — cannot reach host
 *   RedfishTLSError         — TLS handshake failed
 *   RedfishAuthError        — bad credentials (and no fallback configured)
 *   RedfishProtocolError    — unexpected server response
 */
std::unique_ptr<ClientContext> connect(
    const std::string&       host,
    int                      port,
    const Credentials&       credentials,
    AuthMode                 auth_mode,
    const ConnectionConfig&  config = ConnectionConfig{}
);

} // namespace redfish
