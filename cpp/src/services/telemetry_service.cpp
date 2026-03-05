/**
 * src/services/telemetry_service.cpp
 */

#include "redfish_sdk/services/telemetry_service.hpp"
#include "redfish_sdk/transport/auth.hpp"

namespace redfish {

TelemetryServiceHandle::TelemetryServiceHandle(
    HttpClient&                              http,
    const AuthState&                         auth_state,
    const std::map<std::string, std::string>& discovery_map
)
    : http_(http), auth_state_(auth_state), discovery_map_(discovery_map)
{}

std::string TelemetryServiceHandle::service_uri() const {
    auto it = discovery_map_.find("TelemetryService");
    return it != discovery_map_.end() ? it->second : "/redfish/v1/TelemetryService";
}

RedfishResponse TelemetryServiceHandle::get_service_info() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri(), headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse TelemetryServiceHandle::list_metric_definitions() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri() + "/MetricDefinitions", headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse TelemetryServiceHandle::list_metric_reports() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri() + "/MetricReports", headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse TelemetryServiceHandle::get_metric_report(const std::string& report_uri) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", report_uri, headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

RedfishResponse TelemetryServiceHandle::list_report_definitions() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("GET", service_uri() + "/MetricReportDefinitions", headers);
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

} // namespace redfish
