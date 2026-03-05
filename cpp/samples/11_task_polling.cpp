/**
 * Sample 11 — Task polling: wait, monitor, and inspect
 *
 * Demonstrates:
 *   - Triggering an async Redfish task via POST ComputerSystem.Reset
 *   - poll_task() — blocking poll until terminal state or timeout
 *   - Progress callback during polling
 *   - TaskState enum values
 *   - Graceful fallback when no task is returned
 *
 * Usage:
 *   ./11_task_polling [host] [port] [timeout-seconds]
 */
#include "redfish_sdk/client.hpp"
#include "redfish_sdk/errors.hpp"
#include "redfish_sdk/protocol/task.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>
#include <thread>

static const char* task_state_str(redfish::TaskState s) {
    switch (s) {
        case redfish::TaskState::New:         return "New";
        case redfish::TaskState::Starting:    return "Starting";
        case redfish::TaskState::Running:     return "Running";
        case redfish::TaskState::Suspended:   return "Suspended";
        case redfish::TaskState::Interrupted: return "Interrupted";
        case redfish::TaskState::Pending:     return "Pending";
        case redfish::TaskState::Stopping:    return "Stopping";
        case redfish::TaskState::Completed:   return "Completed";
        case redfish::TaskState::Killed:      return "Killed";
        case redfish::TaskState::Exception:   return "Exception";
        case redfish::TaskState::Service:     return "Service";
        default:                              return "Unknown";
    }
}

static void print_task(const redfish::RedfishTask& t, const char* prefix = "") {
    std::cout << "  " << prefix
              << "state=" << std::left << std::setw(14)
              << task_state_str(t.state)
              << " pct=" << t.percent_complete << "%"
              << " uri=" << t.task_uri << "\n";
}

// Returns task_uri or empty string
static std::string trigger_task(redfish::ClientContext& ctx) {
    // Find first ComputerSystem
    auto systems = ctx.get("/redfish/v1/Systems");
    if (!systems.success) return {};
    auto members = systems.body.value("Members", nlohmann::json::array());
    if (members.empty()) return {};

    std::string sys_uri  = members[0].value("@odata.id", "");
    std::string reset_uri = sys_uri + "/Actions/ComputerSystem.Reset";

    // GracefulRestart → most simulators issue a 202 + Location: /redfish/v1/Tasks/…
    auto resp = ctx.post(reset_uri, {{"ResetType", "GracefulRestart"}});
    if (resp.status_code == 202) {
        std::string loc = resp.location();
        if (!loc.empty()) return loc;
        if (resp.body.is_object())
            return resp.body.value("@odata.id", "");
    }

    // Fallback: ForceRestart
    auto resp2 = ctx.post(reset_uri, {{"ResetType", "ForceRestart"}});
    if (resp2.status_code == 202) {
        std::string loc = resp2.location();
        if (!loc.empty()) return loc;
        if (resp2.body.is_object())
            return resp2.body.value("@odata.id", "");
    }
    return {};
}

int main(int argc, char* argv[]) {
    std::string host       = (argc > 1) ? argv[1] : "127.0.0.1";
    int         port       = (argc > 2) ? std::stoi(argv[2]) : 8000;
    long        timeout_s  = (argc > 3) ? std::stol(argv[3]) : 60;

    redfish::Credentials     creds{"admin", "admin"};
    redfish::ConnectionConfig config;
    config.verify_tls = false;

    try {
        auto ctx = redfish::connect(host, port, creds,
                                    redfish::AuthMode::SESSION, config);

        // ── Attempt to create a task ──────────────────────────────────
        std::cout << "Attempting to trigger a task via ComputerSystem.Reset …\n";
        std::string task_uri = trigger_task(*ctx);

        if (task_uri.empty()) {
            std::cout << "  No task returned by this endpoint\n";
            std::cout << "  Listing existing tasks …\n";

            auto tasks_resp = ctx->get("/redfish/v1/TaskService/Tasks");
            if (tasks_resp.success) {
                auto members = tasks_resp.body.value("Members",
                                                     nlohmann::json::array());
                std::cout << "  Existing tasks: " << members.size() << "\n";
                for (std::size_t i = 0; i < members.size() && i < 3; ++i)
                    std::cout << "    " << members[i].value("@odata.id","") << "\n";
            }
            std::cout << "\n✓ Task polling sample complete (no live task available)\n";
            return 0;
        }

        std::cout << "  Task URI: " << task_uri << "\n";

        // ── Demo: poll_task with progress callback ────────────────────
        std::cout << "\n── poll_task(timeout=" << timeout_s << "s) ──\n";
        int snapshots = 0;
        try {
            auto final_resp = redfish::poll_task(
                ctx->http_client(),
                ctx->auth_state(),
                task_uri,
                /*poll_interval_sec=*/2,
                /*timeout_sec=*/timeout_s,
                [&](const redfish::RedfishTask& t) {
                    ++snapshots;
                    print_task(t, "[progress] ");
                }
            );
            std::cout << "  ✓ Finished  HTTP " << final_resp.status_code
                      << "  snapshots=" << snapshots << "\n";
        } catch (const redfish::RedfishError& ex) {
            std::cout << "  ✗ " << ex.what() << "\n";
        }

        // ── Show TaskState enum values ────────────────────────────────
        std::cout << "\n── TaskState values ──\n";
        const redfish::TaskState states[] = {
            redfish::TaskState::New,         redfish::TaskState::Starting,
            redfish::TaskState::Running,     redfish::TaskState::Suspended,
            redfish::TaskState::Interrupted, redfish::TaskState::Pending,
            redfish::TaskState::Stopping,    redfish::TaskState::Completed,
            redfish::TaskState::Killed,      redfish::TaskState::Exception,
            redfish::TaskState::Service
        };
        for (const auto& s : states)
            std::cout << "  " << task_state_str(s) << "\n";

        std::cout << "\n✓ Task polling sample complete\n";
        return 0;
    } catch (const redfish::RedfishError& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
    }
    return 1;
}
