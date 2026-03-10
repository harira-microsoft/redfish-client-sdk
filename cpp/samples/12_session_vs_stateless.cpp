// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * Sample 12 — Session vs Stateless
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>

static void run(const std::string& host, int port, redfish::AuthMode mode, const std::string& label, bool use_tls) {
    redfish::Credentials creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    config.use_tls = use_tls;

    try {
        auto ctx = redfish::connect(host, port, creds, mode, config);
        auto resp = ctx->get("/redfish/v1");
        std::cout << label << ": HTTP " << resp.status_code
                  << (resp.success ? " ✓" : " ✗") << "\n";
    } catch (const redfish::RedfishError& e) {
        std::cout << label << ": ERROR — " << e.what() << "\n";
    }
}

int main(int argc, char* argv[]) {
    std::string host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::stoi(argv[2]) : 8000;
    bool        use_tls = true;
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") use_tls = false;

    run(host, port, redfish::AuthMode::SESSION,   "SESSION   ", use_tls);
    run(host, port, redfish::AuthMode::STATELESS, "STATELESS ", use_tls);

    std::cout << "\n✓ Session vs stateless comparison complete\n";
    return 0;
}
