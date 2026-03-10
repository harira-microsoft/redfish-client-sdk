// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/services/log_service.hpp
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"
#include <functional>
#include <map>
#include <optional>
#include <string>

namespace redfish {

/**
 * OData query parameters for log entry retrieval.
 *
 * Parameters are emitted in the order required by OpenBMC:
 *   $skip  →  $top  →  $filter   (FR6.7)
 *
 * `odata_filter` is a raw escape-hatch that overrides `severity`
 * and `message_id` when set.
 */
struct LogQuery {
    std::optional<int>         top;           // $top  — max entries returned
    std::optional<int>         skip;          // $skip — first N entries to skip
    std::optional<std::string> severity;      // $filter=Severity eq '<value>'
    std::optional<std::string> message_id;    // $filter=MessageId eq '<value>'
    std::optional<std::string> odata_filter;  // raw $filter (overrides severity/message_id)
};

class LogServiceHandle {
public:
    LogServiceHandle(
        IHttpClient&                             http,
        const AuthState&                         auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    RedfishResponse list_services();

    // Fetch one page of entries.
    // Query string is built in required order: $skip → $top → $filter (FR6.7)
    RedfishResponse list_entries(
        const std::string& log_uri,
        const LogQuery&    query = {}
    );

    // Follow Members@odata.nextLink until on_page returns false or pages end.
    // on_page receives one RedfishResponse per page; return false to stop. (FR6.8)
    void iter_entries(
        const std::string&                          log_uri,
        std::function<bool(const RedfishResponse&)> on_page,
        const LogQuery&                             query = {}
    );

    RedfishResponse get_entry(const std::string& entry_uri);
    RedfishResponse clear_log(const std::string& log_uri);

private:
    IHttpClient&                             http_;
    const AuthState&                         auth_state_;
    const std::map<std::string, std::string>& discovery_map_;

    // Build OData query string from LogQuery in required order.
    static std::string build_query_string(const LogQuery& q);
};

} // namespace redfish
