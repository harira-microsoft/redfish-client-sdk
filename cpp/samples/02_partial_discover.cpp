// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * Sample 02 — Partial Discovery
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>

int main(int argc, char* argv[]) {
    std::string host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::stoi(argv[2]) : 8000;

    redfish::Credentials creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP

    try {
        auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION, config);
        auto& disc = ctx->discovery();
        std::cout << "Redfish version: " << disc.redfish_version << "\n";
        std::cout << "Services: " << disc.service_map.size() << " found\n";
        std::cout << "\n✓ Partial discovery complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
