// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/transport/auth.hpp
 *
 * AuthManager — handles SESSION and STATELESS auth.
 * Mirrors Python SDK transport/auth.py.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include <map>
#include <string>

namespace redfish {

class AuthManager {
public:
    AuthManager(
        IHttpClient&       http,
        const Credentials& credentials,
        AuthMode           mode
    );

    // Authenticate and return an AuthState. Throws RedfishAuthError on failure.
    AuthState authenticate();

    // Attach auth headers to an existing header map (mutates in place)
    static void attach_auth(
        const AuthState&                    state,
        std::map<std::string, std::string>& headers
    );

    // DELETE the session on logout (SESSION mode only)
    void logout(const AuthState& state);

private:
    IHttpClient& http_;
    Credentials  credentials_;
    AuthMode     mode_;

    AuthState    session_auth();
    AuthState    stateless_auth();
};

} // namespace redfish
