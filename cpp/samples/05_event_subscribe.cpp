// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * Sample 05 — Event Subscribe
 *
 * Demonstrates:
 *   - subscribe() with EventTypes filter
 *   - subscribe() with MessageIds filter  <-- key for precise event scoping
 *   - list_subscriptions()
 *   - get_subscription()
 *   - submit_test_event()
 *   - delete_subscription()
 *
 * MessageIds is the Redfish 1.5+ recommended approach to receive only events
 * whose MessageId matches a registry-qualified ID such as:
 *     "Base.1.8.Success", "OpenBMC.0.1.PowerButtonPressed"
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>
#include <string>
#include <vector>

static std::string extract_uri(const redfish::RedfishResponse& r) {
    auto loc = r.location();
    if (!loc.empty()) return loc;
    if (r.body.is_object()) return r.body.value("@odata.id", "");
    return {};
}

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
        auto& ev = ctx->events();

        std::vector<std::string> sub_uris;
        const std::string dest = "http://YOUR_LISTENER_HOST:9090/events";

        // ── Subscription 1 — filter by EventTypes ────────────────────
        std::cout << "[1] Creating EventTypes subscription\n";
        auto sub1 = ev.subscribe(dest,
                                 {"Alert", "ResourceUpdated"},   // event_types
                                 {},                              // registry_prefixes
                                 {},                              // message_ids
                                 {},                              // resource_types
                                 "",                             // event_format_type
                                 "CPP-SDK-Sample-05-EventTypes"); // context
        if (sub1.success) {
            auto uri = extract_uri(sub1);
            std::cout << "  ✓ Subscribed: " << uri << "\n";
            if (!uri.empty()) sub_uris.push_back(uri);
        } else {
            std::cout << "  ✗ Subscribe failed: HTTP " << sub1.status_code << "\n";
        }

        // ── Subscription 2 — filter by MessageIds ────────────────────
        // Pass specific registry-qualified MessageIds; leave event_types empty.
        // The BMC will only deliver events whose MessageId is in this list.
        std::vector<std::string> target_ids = {
            "Base.1.8.Success",
            "Base.1.8.GeneralError",
            "OpenBMC.0.1.PowerButtonPressed",
        };
        std::cout << "\n[2] Creating MessageIds subscription\n";
        std::cout << "    MessageIds filter:";
        for (auto& id : target_ids) std::cout << " " << id;
        std::cout << "\n";

        auto sub2 = ev.subscribe(dest,
                                 {},           // event_types  — omit when using MessageIds
                                 {},           // registry_prefixes
                                 target_ids,   // message_ids  <-- filtered set
                                 {},           // resource_types
                                 "",           // event_format_type
                                 "CPP-SDK-Sample-05-MessageIds"); // context
        if (sub2.success) {
            auto uri = extract_uri(sub2);
            std::cout << "  ✓ Subscribed: " << uri << "\n";
            if (!uri.empty()) sub_uris.push_back(uri);
        } else {
            std::cout << "  ✗ Subscribe failed: HTTP " << sub2.status_code << "\n";
        }

        // ── SubmitTestEvent ───────────────────────────────────────────
        auto te = ev.submit_test_event();
        std::cout << "\n" << (te.success ? "✓" : "✗")
                  << " SubmitTestEvent: HTTP " << te.status_code << "\n";

        // ── Delete all created subscriptions ─────────────────────────
        std::cout << "\nDeleting " << sub_uris.size() << " subscription(s) …\n";
        for (auto& uri : sub_uris) {
            auto del = ev.delete_subscription(uri);
            std::cout << "  " << (del.success ? "✓" : "✗")
                      << " Delete " << uri << ": HTTP " << del.status_code << "\n";
        }

        std::cout << "\n✓ Event subscription sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
