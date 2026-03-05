#pragma once
/**
 * redfish_sdk/models/redfish_types.hpp
 *
 * Core value types shared across all SDK layers.
 * No dependencies on transport or protocol headers.
 */

#include <chrono>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace redfish {

// ── Auth ─────────────────────────────────────────────────────────────────────

enum class AuthMode {
    SESSION,    // POST /SessionService/Sessions → X-Auth-Token
    STATELESS,  // Basic auth on every request
};

struct Credentials {
    std::string username;
    std::string password;
};

struct AuthState {
    AuthMode    mode;
    std::string token;          // X-Auth-Token (SESSION) or empty (STATELESS)
    std::string session_uri;    // /redfish/v1/SessionService/Sessions/{id}
    Credentials credentials;    // kept for STATELESS or re-auth
};

// ── TLS ──────────────────────────────────────────────────────────────────────

struct TLSConfig {
    bool        verify      = true;
    std::string ca_cert;        // path to CA bundle, empty = system default
    std::string client_cert;    // mTLS client cert path
    std::string client_key;     // mTLS client key path
};

// ── Timeouts ─────────────────────────────────────────────────────────────────

struct TimeoutConfig {
    long connect_sec        = 10;
    long request_sec        = 30;
    long task_poll_sec      = 5;
    long task_timeout_sec   = 300;
};

// ── Connection config ────────────────────────────────────────────────────────

struct ConnectionConfig {
    bool        verify_tls              = true;
    std::string tls_ca_cert;
    std::string tls_client_cert;
    std::string tls_client_key;
    long        connect_timeout_sec     = 10;
    long        request_timeout_sec     = 30;
    long        task_poll_interval_sec  = 5;
    long        task_timeout_sec        = 300;
    bool        allow_session_fallback  = false;
};

// ── Capabilities ─────────────────────────────────────────────────────────────

struct EndpointCapabilities {
    bool has_systems        = false;
    bool has_managers       = false;
    bool has_chassis        = false;
    bool has_event_service  = false;
    bool has_telemetry      = false;
    bool has_update_service = false;
    bool has_log_service    = false;
    bool has_session_service= false;
    bool has_account_service= false;
    bool has_task_service   = false;
};

// ── Raw HTTP response (internal) ─────────────────────────────────────────────

struct RawHttpResponse {
    int                                 status_code = 0;
    std::map<std::string, std::string>  headers;
    std::string                         body_text;
    // Parsed JSON stored as string; callers parse with nlohmann::json
    std::string                         body_json_str;
    bool                                is_json = false;
};

} // namespace redfish
