/**
 * Sample 06 — Event Listener
 *
 * Demonstrates:
 *   - RedfishEventListener construction
 *   - listener.use_context(ctx)
 *   - listener.on_event() global callback
 *   - listener.start() / listener.stop()
 *   - Auto-subscribe with listener.listen_url() as destination
 *   - Waiting for events then cleaning up
 *
 * Usage:
 *   ./06_event_listener [host] [port] [listen-port] [wait-seconds]
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
    uint16_t    listen_port = (argc > 3) ? static_cast<uint16_t>(std::stoi(argv[3])) : 9090;
    int         wait_sec    = (argc > 4) ? std::stoi(argv[4]) : 10;

    redfish::Credentials    creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP

    try {
        auto ctx = redfish::connect(host, port, creds,
                                    redfish::AuthMode::SESSION, config);

        // ── Build listener ─────────────────────────────────────────────
        redfish::RedfishEventListener listener{listen_port, "0.0.0.0",
                                               "RSDK-Sample-06"};
        listener.use_context(*ctx);

        std::atomic<int> received{0};

        listener.on_event([&](const redfish::RedfishEvent& ev) {
            ++received;
            std::cout << "  [EVENT] type=" << ev.event_type
                      << "  id=" << ev.message_id << "\n"
                      << "          msg=" << ev.message << "\n"
                      << "          sev=" << ev.severity << "\n";
        });

        listener.start();
        std::string url = listener.listen_url();
        std::cout << "✓ Listener running at " << url << "\n";

        // ── Subscribe ─────────────────────────────────────────────────
        // Use 127.0.0.1 as the destination so the simulator can reach us.
        std::string dest = "http://127.0.0.1:" + std::to_string(listen_port)
                           + "/events";
        std::cout << "Subscribing → " << dest << "\n";

        auto& ev_svc = ctx->events();
        auto  sub    = ev_svc.subscribe(dest,
                                         {"Alert", "ResourceUpdated"},
                                         {}, {}, {}, "",
                                         "RSDK-Sample-06");
        std::string sub_uri;
        if (sub.success) {
            sub_uri = sub.location();
            if (sub_uri.empty() && sub.body.is_object())
                sub_uri = sub.body.value("@odata.id", "");
            std::cout << "  ✓ Subscribed: " << sub_uri << "\n";
        } else {
            std::cout << "  ✗ Subscribe failed HTTP " << sub.status_code << "\n";
        }

        // ── Trigger a test event ──────────────────────────────────────
        std::cout << "Submitting test event …\n";
        ev_svc.submit_test_event();

        // ── Wait ──────────────────────────────────────────────────────
        std::cout << "Waiting " << wait_sec << "s for events …\n";
        std::this_thread::sleep_for(std::chrono::seconds(wait_sec));

        std::cout << "\nReceived " << received.load() << " event(s) in "
                  << wait_sec << "s\n";

        // ── Buffered events via GET ───────────────────────────────────
        auto buffered = listener.get_buffered_events();
        std::cout << "Buffered events in ring buffer: " << buffered.size() << "\n";

        // ── IP stats ──────────────────────────────────────────────────
        auto stats = listener.get_ip_stats();
        for (const auto& [ip, count] : stats)
            std::cout << "  IP " << ip << " → " << count << " event(s)\n";

        // ── Cleanup ───────────────────────────────────────────────────
        if (!sub_uri.empty()) {
            ev_svc.delete_subscription(sub_uri);
            std::cout << "✓ Subscription deleted\n";
        }
        listener.stop();
        std::cout << "✓ Listener stopped\n";

        std::cout << "\n✓ Event listener sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
