/**
 * Sample 05 — Event Subscribe
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
        auto& ev = ctx->events();

        // Subscribe
        auto sub = ev.subscribe("http://192.168.1.10:9090/events",
                                {"Alert", "ResourceUpdated"},
                                {}, {}, "CPP-SDK-Sample-05");
        std::string sub_uri;
        if (sub.success) {
            sub_uri = sub.location();
            if (sub_uri.empty() && sub.body.is_object())
                sub_uri = sub.body.value("@odata.id", "");
            std::cout << "✓ Subscribed: " << sub_uri << "\n";
        } else {
            std::cout << "✗ Subscribe failed: HTTP " << sub.status_code << "\n";
        }

        // SubmitTestEvent
        auto te = ev.submit_test_event();
        std::cout << (te.success ? "✓" : "✗")
                  << " SubmitTestEvent: HTTP " << te.status_code << "\n";

        // Delete
        if (!sub_uri.empty()) {
            auto del = ev.delete_subscription(sub_uri);
            std::cout << (del.success ? "✓" : "✗")
                      << " Delete: HTTP " << del.status_code << "\n";
        }

        std::cout << "\n✓ Event subscription sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
