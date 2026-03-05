/**
 * src/client.cpp
 *
 * SDK entry point implementation — v0.2
 */

#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/transport/tls.hpp"
#include "redfish_sdk/discovery/discovery.hpp"
#include "internal/logger.hpp"
#include <curl/curl.h>

namespace redfish {

// Best-effort plain-HTTP probe of /redfish/v1 for initial service discovery.
// Non-fatal: if the server only speaks HTTPS the probe is skipped silently.
static void http_probe(const std::string& host, int port,
                       const std::string& path, long timeout_sec) {
    CURL* curl = curl_easy_init();
    if (!curl) return;
    std::string url = "http://" + host + ":" + std::to_string(port) + path;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_NOBODY, 1L); // HEAD-style, discard body
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, timeout_sec);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_sec);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    CURLcode res = curl_easy_perform(curl);
    long code = 0;
    if (res == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &code);
    curl_easy_cleanup(curl);
    if (res == CURLE_OK)
        REDFISH_LOG_DEBUG("client", "HTTP probe " + url + " -> HTTP " + std::to_string(code));
    else
        REDFISH_LOG_DEBUG("client", "HTTP probe " + url + " failed (non-fatal): " + curl_easy_strerror(res));
}

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

    // Always HTTPS. verify_tls controls cert verification, not the protocol.
    std::string base_url = "https://" + host + ":" + std::to_string(port);

    // Non-fatal HTTP probe for service discovery (/redfish/v1 is often HTTP)
    http_probe(host, port, "/redfish/v1", timeouts.connect_sec);

    REDFISH_LOG_DEBUG("client", "Connecting to " + base_url);
    auto http = std::make_unique<DefaultHttpClient>(base_url, tls, timeouts, config);

    AuthState auth_state;
    try {
        AuthManager mgr(*http, credentials, auth_mode);
        auth_state = mgr.authenticate();
        REDFISH_LOG_DEBUG("client", "Authenticated");
    } catch (const RedfishAuthError&) {
        if (auth_mode == AuthMode::SESSION && config.allow_session_fallback) {
            REDFISH_LOG_INFO("client", "SESSION auth failed; retrying as STATELESS");
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
