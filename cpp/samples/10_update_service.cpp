/**
 * Sample 10 — UpdateService: firmware inventory and SimpleUpdate
 *
 * Demonstrates:
 *   - update.list_firmware_inventory()
 *   - update.get_firmware_component()
 *   - update.simple_update() and receiving a RedfishTask
 *   - Task polling via poll_task()
 *
 * NOTE: SimpleUpdate triggers an actual firmware update.  Use a simulator
 *       or non-production BMC.  Pass --dry-run to skip the update call.
 *
 * Usage:
 *   ./10_update_service [host] [port] [image-uri] [--dry-run]
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include "redfish_sdk/protocol/task.hpp"
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

// Simple arg helper
static bool has_flag(int argc, char* argv[], const std::string& flag) {
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == flag) return true;
    return false;
}

int main(int argc, char* argv[]) {
    std::string host      = (argc > 1 && argv[1][0] != '-') ? argv[1] : "127.0.0.1";
    int         port      = (argc > 2 && argv[2][0] != '-') ? std::stoi(argv[2]) : 8000;
    std::string image_uri = (argc > 3 && argv[3][0] != '-')
                                ? argv[3]
                                : "http://fileserver.example.com/firmware.bin";
    bool        dry_run   = has_flag(argc, argv, "--dry-run");

    redfish::Credentials     creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;  // disable cert verification for simulator (self-signed)
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--no-tls") config.use_tls = false;  // plain HTTP

    try {
        auto ctx = redfish::connect(host, port, creds,
                                    redfish::AuthMode::SESSION, config);
        auto& update = ctx->update();

        // ── Firmware inventory ────────────────────────────────────────
        std::cout << "Firmware inventory:\n";
        auto fw_resp = update.list_firmware_inventory();
        std::string first_target;
        if (fw_resp.success) {
            auto members = fw_resp.body.value("Members",
                                              nlohmann::json::array());
            std::cout << "  Items: " << members.size() << "\n";
            for (const auto& item : members) {
                std::string uri = item.value("@odata.id", "");
                auto detail = ctx->get(uri);
                if (detail.success) {
                    auto& b = detail.body;
                    std::cout << "    "
                              << std::left << std::setw(20)
                              << b.value("Id","?")
                              << std::setw(30)
                              << b.value("Name","")
                              << " v" << b.value("Version","?")
                              << "\n";
                }
                if (first_target.empty()) first_target = uri;
            }
        } else {
            std::cout << "  ✗ HTTP " << fw_resp.status_code << "\n";
        }

        // ── SimpleUpdate ──────────────────────────────────────────────
        std::vector<std::string> targets;
        if (!first_target.empty()) targets.push_back(first_target);

        if (dry_run) {
            std::cout << "\n[DRY RUN] Skipping SimpleUpdate call\n";
        } else {
            std::cout << "\nCalling SimpleUpdate:\n";
            std::cout << "  ImageURI : " << image_uri << "\n";
            std::cout << "  Targets  : ";
            for (const auto& t : targets) std::cout << t << " ";
            std::cout << "\n";

            try {
                auto resp = update.simple_update(image_uri, "HTTP", targets);
                if (resp.success) {
                    std::string task_uri = resp.location();
                    if (task_uri.empty() && resp.body.is_object())
                        task_uri = resp.body.value("@odata.id", "");

                    if (!task_uri.empty()) {
                        std::cout << "  ✓ Task created: " << task_uri << "\n";
                        std::cout << "  Monitoring task (30s timeout) …\n";

                        // Poll the task
                        auto final_resp = redfish::poll_task(
                            ctx->http_client(),
                            ctx->auth_state(),
                            task_uri,
                            /*poll_interval_sec=*/2,
                            /*timeout_sec=*/30,
                            [](const redfish::RedfishTask& t) {
                                std::cout << "    state=" << t.messages
                                          << "  " << t.percent_complete
                                          << "%\n";
                            }
                        );
                        std::cout << "  ✓ Task finished  HTTP "
                                  << final_resp.status_code << "\n";
                    } else {
                        std::cout << "  ✓ Update completed synchronously"
                                  << " (HTTP " << resp.status_code << ")\n";
                    }
                } else {
                    std::cout << "  ✗ SimpleUpdate HTTP "
                              << resp.status_code << "\n";
                    std::cout << "    (Simulator may not implement SimpleUpdate)\n";
                }
            } catch (const std::exception& ex) {
                std::cout << "  ✗ SimpleUpdate error: " << ex.what() << "\n";
            }
        }

        std::cout << "\n✓ Update service sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
