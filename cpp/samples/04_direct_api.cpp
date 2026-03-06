/**
 * Sample 04 — Direct API
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

        // GET root
        auto r1 = ctx->get("/redfish/v1");
        std::cout << (r1.success ? "✓" : "✗")
                  << " [" << r1.status_code << "] GET /redfish/v1\n";

        // PATCH Systems
        nlohmann::json patch_body = {{"AssetTag", "CPP-SDK-Test"}};
        auto r2 = ctx->patch("/redfish/v1/Systems/system", patch_body);
        std::cout << (r2.success ? "✓" : "✗")
                  << " [" << r2.status_code << "] PATCH AssetTag\n";

        std::cout << "\n✓ Direct API sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
