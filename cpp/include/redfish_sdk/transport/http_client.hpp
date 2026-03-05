#pragma once
/**
 * redfish_sdk/transport/http_client.hpp
 *
 * Wraps libcurl. Provides a uniform synchronous request interface.
 * Async is achieved by callers using std::async / std::future.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include <string>
#include <map>
#include <optional>

namespace redfish {

class HttpClient {
public:
    HttpClient(
        const std::string&   base_url,
        const TLSConfig&     tls,
        const TimeoutConfig& timeouts
    );
    ~HttpClient();

    // Non-copyable, movable
    HttpClient(const HttpClient&)            = delete;
    HttpClient& operator=(const HttpClient&) = delete;
    HttpClient(HttpClient&&)                 = default;

    RawHttpResponse request(
        const std::string&                         method,
        const std::string&                         path,
        const std::map<std::string, std::string>&  headers = {},
        const std::optional<std::string>&          body    = std::nullopt
    );

    const std::string& base_url() const { return base_url_; }

private:
    std::string   base_url_;
    TLSConfig     tls_;
    TimeoutConfig timeouts_;
};

} // namespace redfish
