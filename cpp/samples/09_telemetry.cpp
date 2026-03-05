/**
 * Sample 09 — Telemetry
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
        auto& tel = ctx->telemetry();

        auto svc = tel.get_service_info();
        std::cout << (svc.success ? "✓" : "✗")
                  << " TelemetryService: HTTP " << svc.status_code << "\n";

        auto reports = tel.list_metric_reports();
        if (reports.success)
            std::cout << "  MetricReports: "
                      << reports.body.value("Members@odata.count", 0) << "\n";

        std::cout << "\n✓ Telemetry sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
