/**
 * src/transport/auth.cpp
 */

#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/errors.hpp"
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace redfish {

static std::string base64_encode(const std::string& input) {
    static const char table[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    int val = 0, valb = -6;
    for (unsigned char c : input) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) {
            out.push_back(table[(val >> valb) & 0x3F]);
            valb -= 6;
        }
    }
    if (valb > -6) out.push_back(table[((val << 8) >> (valb + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

AuthManager::AuthManager(
    HttpClient&        http,
    const Credentials& credentials,
    AuthMode           mode
)
    : http_(http), credentials_(credentials), mode_(mode)
{}

AuthState AuthManager::authenticate() {
    if (mode_ == AuthMode::SESSION)   return session_auth();
    if (mode_ == AuthMode::STATELESS) return stateless_auth();
    throw RedfishAuthError("Unknown AuthMode");
}

AuthState AuthManager::session_auth() {
    nlohmann::json payload = {
        {"UserName", credentials_.username},
        {"Password", credentials_.password},
    };
    auto body_str = payload.dump();

    auto raw = http_.request("POST", "/redfish/v1/SessionService/Sessions",
                             {}, body_str);

    if (raw.status_code != 200 && raw.status_code != 201 && raw.status_code != 204) {
        throw RedfishAuthError(
            "Session auth failed — HTTP " + std::to_string(raw.status_code));
    }

    auto token_it = raw.headers.find("x-auth-token");
    if (token_it == raw.headers.end() || token_it->second.empty())
        throw RedfishAuthError("Session created but no X-Auth-Token in response");

    auto loc_it = raw.headers.find("location");
    std::string session_uri = (loc_it != raw.headers.end()) ? loc_it->second : "";

    AuthState state;
    state.mode        = AuthMode::SESSION;
    state.token       = token_it->second;
    state.session_uri = session_uri;
    state.credentials = credentials_;
    return state;
}

AuthState AuthManager::stateless_auth() {
    // Validate credentials with a lightweight GET
    std::string encoded = base64_encode(credentials_.username + ":" + credentials_.password);
    std::map<std::string, std::string> headers = {
        {"Authorization", "Basic " + encoded}
    };
    auto raw = http_.request("GET", "/redfish/v1", headers);
    if (raw.status_code == 401 || raw.status_code == 403)
        throw RedfishAuthError("Stateless auth rejected — HTTP " + std::to_string(raw.status_code));

    AuthState state;
    state.mode        = AuthMode::STATELESS;
    state.credentials = credentials_;
    return state;
}

// static
void AuthManager::attach_auth(
    const AuthState&                    state,
    std::map<std::string, std::string>& headers
) {
    if (state.mode == AuthMode::SESSION && !state.token.empty()) {
        headers["X-Auth-Token"] = state.token;
    } else if (state.mode == AuthMode::STATELESS) {
        std::string encoded = base64_encode(
            state.credentials.username + ":" + state.credentials.password);
        headers["Authorization"] = "Basic " + encoded;
    }
}

void AuthManager::logout(const AuthState& state) {
    if (state.mode != AuthMode::SESSION || state.session_uri.empty()) return;
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(state, headers);
    try {
        http_.request("DELETE", state.session_uri, headers);
    } catch (...) {
        // Best-effort logout — ignore errors
    }
}

} // namespace redfish
