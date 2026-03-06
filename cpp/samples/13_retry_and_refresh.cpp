/**
 * Sample 13 — Retry and Auth Refresh (v0.2)
 *
 * Demonstrates:
 *   - ConnectionConfig retry fields (FR1.8, FR1.9)
 *   - ctx->refresh_auth()           (FR1.10)
 *
 * Usage:
 *   ./13_retry_and_refresh [host] [port]
 */

#include "redfish_sdk/client.hpp"
#include "redfish_sdk/context.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>
#include <string>

int main(int argc, char* argv[]) {
    std::string host = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port = (argc > 2) ? std::stoi(argv[2]) : 8000;

    redfish::Credentials    creds{"admin", "admin"};

    // FR1.8 / FR1.9 — retry configuration
    redfish::ConnectionConfig config;
    config.verify_tls                  = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP
    config.retry_on_connection_failure = 2;
    config.retry_status_codes          = {503, 429};
    config.retry_delay_sec             = 1.0;

    std::cout << "Connecting with retry config:\n"
              << "  retry_on_connection_failure : " << config.retry_on_connection_failure << "\n"
              << "  retry_status_codes          : [503, 429]\n"
              << "  retry_delay_sec             : " << config.retry_delay_sec << "\n\n";

    try {
        auto ctx = redfish::connect(host, port, creds, redfish::AuthMode::SESSION, config);

        auto& disc = ctx->discovery();
        std::cout << "Connected — Redfish " << disc.redfish_version << "\n";

        // FR1.10 — refresh auth (re-authenticate with stored credentials)
        std::cout << "Calling refresh_auth()...\n";
        ctx->refresh_auth();
        std::cout << "  Auth token refreshed\n";

        // Verify session is still functional after refresh
        auto resp = ctx->get("/redfish/v1");
        std::cout << "  GET /redfish/v1 after refresh -> HTTP " << resp.status_code
                  << (resp.success ? " OK" : " FAIL") << "\n";

        std::cout << "\n✓ Retry and refresh sample complete\n";
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
