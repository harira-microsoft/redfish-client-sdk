/**
 * src/client.cpp
 *
 * SDK entry point implementation.
 */

#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/transport/tls.hpp"
#include "redfish_sdk/discovery/discovery.hpp"

namespace redfish {

std::unique_ptr<ClientContext> connect(
    const std::string&      host,
    int                     port,
    const Credentials&      credentials,
    AuthMode                auth_mode,
    const ConnectionConfig& config
) {
    TimeoutConfig timeouts{
        config.connect_timeout_sec,
        config.request_timeout_sec,
        config.task_poll_interval_sec,
        config.task_timeout_sec,
    };

    TLSConfig tls = build_tls_config(config);

    // Use http:// when verify_tls=false and no CA cert — plain HTTP (e.g. simulator)
    bool use_https = config.verify_tls || !config.tls_ca_cert.empty();
    std::string scheme = use_https ? "https" : "http";
    std::string base_url = scheme + "://" + host + ":" + std::to_string(port);

    auto http = std::make_unique<HttpClient>(base_url, tls, timeouts);

    AuthState auth_state;
    try {
        AuthManager mgr(*http, credentials, auth_mode);
        auth_state = mgr.authenticate();
    } catch (const RedfishAuthError&) {
        if (auth_mode == AuthMode::SESSION && config.allow_session_fallback) {
            AuthManager fallback(*http, credentials, AuthMode::STATELESS);
            auth_state = fallback.authenticate();
        } else {
            throw;
        }
    }

    Discovery disc(*http, auth_state);
    auto discovery = disc.discover();

    return std::make_unique<ClientContext>(
        std::move(http),
        std::move(auth_state),
        std::move(discovery),
        config
    );
}

} // namespace redfish
