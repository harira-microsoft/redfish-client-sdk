/**
 * src/protocol/task.cpp
 */

#include "redfish_sdk/protocol/task.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/errors.hpp"
#include <thread>
#include <chrono>

namespace redfish {

static TaskState parse_task_state(const std::string& s) {
    if (s == "Completed")   return TaskState::Completed;
    if (s == "Exception")   return TaskState::Exception;
    if (s == "Killed")      return TaskState::Killed;
    if (s == "Running")     return TaskState::Running;
    if (s == "Starting")    return TaskState::Starting;
    if (s == "Pending")     return TaskState::Pending;
    if (s == "Stopping")    return TaskState::Stopping;
    if (s == "Suspended")   return TaskState::Suspended;
    return TaskState::New;
}

RedfishResponse poll_task(
    IHttpClient&             http,
    const AuthState&         auth_state,
    const std::string&       task_uri,
    long                     poll_interval_sec,
    long                     timeout_sec,
    std::function<void(const RedfishTask&)> on_progress
) {
    auto start = std::chrono::steady_clock::now();

    while (true) {
        std::map<std::string, std::string> headers;
        AuthManager::attach_auth(auth_state, headers);
        auto raw  = http.request("GET", task_uri, headers);
        auto resp = build_response(raw.status_code, raw.headers, raw.body_text);

        RedfishTask task;
        task.task_uri = task_uri;

        if (resp.success && !resp.body.is_null()) {
            task.task_id          = resp.body.value("Id", "");
            task.state            = parse_task_state(resp.body.value("TaskState", ""));
            task.percent_complete = resp.body.value("PercentComplete", 0);
            task.start_time       = resp.body.value("StartTime", "");
            task.end_time         = resp.body.value("EndTime", "");

            if (on_progress) on_progress(task);

            if (task.state == TaskState::Completed ||
                task.state == TaskState::Exception  ||
                task.state == TaskState::Killed)
                return resp;
        } else {
            return resp;  // HTTP error — return as-is
        }

        auto elapsed = std::chrono::steady_clock::now() - start;
        if (std::chrono::duration_cast<std::chrono::seconds>(elapsed).count() >= timeout_sec)
            throw RedfishTimeoutError("Task " + task_uri + " timed out");

        std::this_thread::sleep_for(std::chrono::seconds(poll_interval_sec));
    }
}

} // namespace redfish
