/**
 * Sample 07 — Event Monitor (filtered callbacks)
 *
 * Demonstrates:
 *   - listener.on_event_type(type, callback)   — EventType-filtered callback
 *   - listener.on_registry(prefix, callback)   — registry-prefix-filtered callback
 *   - Combining multiple callback registrations
 *   - get_ip_stats() / get_buffered_events()
 *
 * Usage:
 *   ./07_event_monitor [host] [port] [listen-port] [wait-seconds]
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include "redfish_sdk/event_listener.hpp"
#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>

int main(int argc, char* argv[]) {
    std::string host        = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port        = (argc > 2) ? std::stoi(argv[2]) : 8000;
    uint16_t    listen_port = (argc > 3) ? static_cast<uint16_t>(std::stoi(argv[3])) : 9091;
    int         wait_sec    = (argc > 4) ? std::stoi(argv[4]) : 15;

    redfish::Credentials     creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP

    try {
        auto ctx = redfish::connect(host, port, creds,
                                    redfish::AuthMode::SESSION, config);

        redfish::RedfishEventListener listener{listen_port};
        listener.use_context(*ctx);

        std::atomic<int> total{0}, alerts{0}, base_msgs{0};

        // ── Global catch-all ──────────────────────────────────────────
        listener.on_event([&](const redfish::RedfishEvent& ev) {
            ++total;
            std::cout << "  [ALL   ] " << ev.event_type
                      << " — " << ev.message_id << "\n";
        });

        // ── EventType-filtered: Alert only ────────────────────────────
        listener.on_event_type("Alert", [&](const redfish::RedfishEvent& ev) {
            ++alerts;
            std::cout << "  [ALERT ] " << ev.message << "\n";
        });

        // ── Registry-prefix-filtered: Base.* messages ─────────────────
        listener.on_registry("Base", [&](const redfish::RedfishEvent& ev) {
            ++base_msgs;
            std::cout << "  [BASE  ] id=" << ev.message_id << "\n";
        });

        // ── OpenBMC registry ──────────────────────────────────────────
        listener.on_registry("OpenBMC", [&](const redfish::RedfishEvent& ev) {
            std::cout << "  [OPENBMC] " << ev.message_id
                      << "  sev=" << ev.severity << "\n";
        });

        listener.start();
        std::cout << "✓ Listener at " << listener.listen_url() << "\n";

        // ── Subscribe ─────────────────────────────────────────────────
        std::string dest = "http://127.0.0.1:" + std::to_string(listen_port)
                           + "/events";
        auto& ev_svc = ctx->events();
        auto  sub    = ev_svc.subscribe(dest,
                                         {"Alert", "ResourceUpdated", "StatusChange"},
                                         {"Base", "OpenBMC"},
                                         {}, {}, "", "RSDK-Sample-07");

        std::string sub_uri;
        if (sub.success) {
            sub_uri = sub.location();
            if (sub_uri.empty() && sub.body.is_object())
                sub_uri = sub.body.value("@odata.id", "");
            std::cout << "  ✓ Subscribed: " << sub_uri << "\n";
        } else {
            std::cout << "  ✗ Subscribe HTTP " << sub.status_code << "\n";
        }

        // Trigger a couple of test events
        ev_svc.submit_test_event();
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        ev_svc.submit_test_event({{"EventType","StatusChange"},
                                   {"MessageId","Base.1.8.Success"},
                                   {"Message","Status change event"}});

        std::cout << "Waiting " << wait_sec << "s …\n";
        std::this_thread::sleep_for(std::chrono::seconds(wait_sec));

        // ── Summary ───────────────────────────────────────────────────
        std::cout << "\n── Event summary ──\n";
        std::cout << "  Total     : " << total.load()    << "\n";
        std::cout << "  Alerts    : " << alerts.load()   << "\n";
        std::cout << "  Base.*    : " << base_msgs.load()<< "\n";
        std::cout << "  Buffered  : " << listener.get_buffered_events().size()
                  << "\n";
        for (const auto& [ip, cnt] : listener.get_ip_stats())
            std::cout << "  IP " << ip << " → " << cnt << "\n";

        // ── Cleanup ───────────────────────────────────────────────────
        if (!sub_uri.empty()) ev_svc.delete_subscription(sub_uri);
        listener.stop();

        std::cout << "\n✓ Event monitor sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
