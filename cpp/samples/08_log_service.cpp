/**
 * Sample 08 — Log Service
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>

int main(int argc, char* argv[]) {
    std::string host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::stoi(argv[2]) : 8000;

    redfish::Credentials creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;

    try {
        auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION, config);
        auto& logs = ctx->logs();

        auto svc = logs.list_services();
        if (svc.success && svc.body.is_object()) {
            std::cout << "Log services found: "
                      << svc.body.value("Members@odata.count", 0) << "\n";
            for (auto& m : svc.body.value("Members", nlohmann::json::array())) {
                auto uri = m.value("@odata.id", "");
                std::cout << "  LogService: " << uri << "\n";
                try {
                    auto entries = logs.list_entries(uri, 5);
                    if (entries.success)
                        std::cout << "    Entries: "
                                  << entries.body.value("Members@odata.count", 0) << "\n";
                    else
                        std::cout << "    Entries: not available (HTTP "
                                  << entries.status_code << ")\n";
                } catch (const redfish::RedfishError& ex) {
                    std::cout << "    Entries: skipped (" << ex.what() << ")\n";
                }
            }
        }

        std::cout << "\n✓ Log service sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
