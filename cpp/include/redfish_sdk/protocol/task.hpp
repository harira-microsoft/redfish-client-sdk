#pragma once
/**
 * redfish_sdk/protocol/task.hpp
 *
 * RedfishTask — represents an async task returned by long-running operations.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include <string>
#include <functional>

namespace redfish {

enum class TaskState {
    New, Starting, Running, Suspended, Interrupted,
    Pending, Stopping, Completed, Killed, Exception, Service
};

struct RedfishTask {
    std::string task_uri;
    std::string task_id;
    TaskState   state       = TaskState::New;
    int         percent_complete = 0;
    std::string start_time;
    std::string end_time;
    std::string messages;
};

// Poll a task URI until completion or timeout.
// Returns the final RedfishResponse of the task resource.
RedfishResponse poll_task(
    IHttpClient&             http,
    const AuthState&         auth_state,
    const std::string&       task_uri,
    long                     poll_interval_sec,
    long                     timeout_sec,
    std::function<void(const RedfishTask&)> on_progress = nullptr
);

} // namespace redfish
