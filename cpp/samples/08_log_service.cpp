// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * Sample 08 — Log Service: $top / $skip / $filter and nextLink pagination
 *
 * Demonstrates:
 *   - logs.list_services()
 *   - LogQuery with top, skip, severity, message_id
 *   - logs.list_entries() — single page
 *   - logs.iter_entries()  — follow Members@odata.nextLink
 *   - logs.clear_log()
 *
 * Usage:
 *   ./08_log_service [host] [port] [max-entries]
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include <iomanip>
#include <iostream>

static void print_entry(const nlohmann::json& e) {
    std::cout << "      [" << std::left << std::setw(10) << e.value("Id","?") << "] "
              << std::setw(12) << e.value("Severity","?")
              << " " << e.value("Created","")
              << "  " << e.value("Message","").substr(0, 72) << "\n";
}

int main(int argc, char* argv[]) {
    std::string host        = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port        = (argc > 2) ? std::stoi(argv[2]) : 8000;
    int         max_entries = (argc > 3) ? std::stoi(argv[3]) : 5;

    redfish::Credentials creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP

    try {
        auto ctx  = redfish::connect(host, port, creds,
                                     redfish::AuthMode::SESSION, config);
        auto& logs = ctx->logs();

        // ── List services ─────────────────────────────────────────────
        auto svc = logs.list_services();
        if (!svc.success || !svc.body.is_object()) {
            std::cout << "No log services found\n";
            return 0;
        }
        auto members = svc.body.value("Members", nlohmann::json::array());
        std::cout << "Log services: " << members.size() << "\n";

        for (const auto& m : members) {
            std::string uri = m.value("@odata.id", "");
            std::cout << "\n  LogService: " << uri << "\n";

            // ── $top=N ───────────────────────────────────────────────
            {
                redfish::LogQuery q;
                q.top = max_entries;
                auto r = logs.list_entries(uri, q);
                auto count = r.success
                    ? r.body.value("Members@odata.count", 0) : 0;
                std::cout << "    $top=" << max_entries
                          << " : returned " << (r.success ? r.body.value("Members", nlohmann::json::array()).size() : 0)
                          << " of " << count << " total\n";
                if (r.success)
                    for (const auto& e : r.body.value("Members", nlohmann::json::array()))
                        print_entry(e);
            }

            // ── $skip + $top ─────────────────────────────────────────
            {
                redfish::LogQuery q;
                q.skip = max_entries;
                q.top  = 2;
                auto r = logs.list_entries(uri, q);
                if (r.success) {
                    auto skipped = r.body.value("Members", nlohmann::json::array());
                    std::cout << "    $skip=" << max_entries << "&$top=2 : "
                              << skipped.size() << " entry(ies)\n";
                    for (const auto& e : skipped) print_entry(e);
                }
            }

            // ── $filter=Severity ─────────────────────────────────────
            {
                redfish::LogQuery q;
                q.severity = "Warning";
                q.top      = 3;
                auto r = logs.list_entries(uri, q);
                if (r.success) {
                    auto w = r.body.value("Members", nlohmann::json::array());
                    std::cout << "    $filter=Severity eq 'Warning': "
                              << w.size() << " entry(ies)\n";
                    for (const auto& e : w) print_entry(e);
                }
            }

            // ── iter_entries: follow nextLink ─────────────────────────
            {
                std::cout << "    iter_entries (page_size=2, max 3 pages) …\n";
                int page = 0, total = 0;
                redfish::LogQuery q;
                q.top = 2;
                logs.iter_entries(uri,
                    [&](const redfish::RedfishResponse& resp) -> bool {
                        ++page;
                        int n = resp.success
                            ? static_cast<int>(resp.body.value("Members",
                                nlohmann::json::array()).size()) : 0;
                        total += n;
                        bool has_next = resp.success &&
                            resp.body.contains("Members@odata.nextLink");
                        std::cout << "      Page " << page
                                  << ": " << n << " entries"
                                  << "  nextLink=" << (has_next ? "yes" : "no")
                                  << "\n";
                        return page < 3;  // stop after 3 pages
                    }, q);
                std::cout << "      Total from " << page << " page(s): "
                          << total << " entries\n";
            }
        }

        // ── Clear first log ───────────────────────────────────────────
        if (!members.empty()) {
            std::string first_uri = members[0].value("@odata.id", "");
            std::cout << "\nClearing: " << first_uri << "\n";
            auto cr = logs.clear_log(first_uri);
            std::cout << (cr.success ? "  ✓ cleared" : "  ✗ not supported")
                      << " (HTTP " << cr.status_code << ")\n";
        }

        std::cout << "\n✓ Log service sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
