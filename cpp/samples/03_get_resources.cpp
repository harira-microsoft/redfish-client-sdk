/**
 * Sample 03 — Get Resources
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

        // Systems
        if (ctx->capabilities().has_systems) {
            auto resp = ctx->get(ctx->discovery().service_map.at("Systems"));
            if (resp.success) {
                std::cout << "Systems count: "
                          << resp.body.value("Members@odata.count", 0) << "\n";
                for (auto& m : resp.body.value("Members", nlohmann::json::array()))
                    std::cout << "  " << m.value("@odata.id", "") << "\n";
            }
        }

        std::cout << "\n✓ Resource GET complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
