/**
 * Sample 01 — Connect and Discover
 *
 * Demonstrates:
 *   - redfish::connect()
 *   - ctx->discovery() — Redfish version, service map
 *   - ctx->capabilities() — endpoint feature flags
 *
 * Usage:
 *   ./01_connect_discover [host] [port]
 */

#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>
#include <string>

int main(int argc, char* argv[]) {
    std::string host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::stoi(argv[2]) : 8000;

    redfish::Credentials    creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // plain HTTP for simulator

    try {
        auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION, config);

        auto& disc = ctx->discovery();
        std::cout << "Redfish version : " << disc.redfish_version << "\n";
        std::cout << "Services found  :\n";
        for (auto& [name, uri] : disc.service_map)
            std::cout << "  " << name << " → " << uri << "\n";

        auto& cap = ctx->capabilities();
        std::cout << "\nCapabilities:\n";
        std::cout << "  Systems        : " << (cap.has_systems         ? "yes" : "no") << "\n";
        std::cout << "  Managers       : " << (cap.has_managers        ? "yes" : "no") << "\n";
        std::cout << "  EventService   : " << (cap.has_event_service   ? "yes" : "no") << "\n";
        std::cout << "  TelemetryService: " << (cap.has_telemetry      ? "yes" : "no") << "\n";
        std::cout << "  UpdateService  : " << (cap.has_update_service  ? "yes" : "no") << "\n";
        std::cout << "  SessionService : " << (cap.has_session_service ? "yes" : "no") << "\n";

        std::cout << "\n✓ Discovery complete\n";
        return 0;

    } catch (const redfish::RedfishConnectionError& e) {
        std::cerr << "[ERROR] Connection: " << e.what() << "\n";
    } catch (const redfish::RedfishAuthError& e) {
        std::cerr << "[ERROR] Auth: " << e.what() << "\n";
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
