// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/transport/http_client.hpp
 *
 * Transport abstraction layer — v0.2
 *
 *   IHttpClient       — abstract base (NFR8.2: injectable/mockable)
 *   DefaultHttpClient — production impl: libcurl + retry (FR1.8, FR1.9)
 *   MockHttpClient    — test double: canned (method, path) → RawHttpResponse
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace redfish {

// ── Abstract base ─────────────────────────────────────────────────────────────

class IHttpClient {
public:
    virtual ~IHttpClient() = default;

    virtual RawHttpResponse request(
        const std::string&                        method,
        const std::string&                        path,
        const std::map<std::string, std::string>& headers = {},
        const std::optional<std::string>&         body    = std::nullopt
    ) = 0;

    // Multipart POST — fields are plain text, files are binary blobs (FR7.5)
    virtual RawHttpResponse request_multipart(
        const std::string&                                    path,
        const std::map<std::string, std::string>&             headers,
        const std::map<std::string, std::string>&             fields,
        const std::map<std::string, std::vector<uint8_t>>&   files = {}
    ) = 0;

    virtual const std::string& base_url() const = 0;
};

// ── Production implementation ────────────────────────────────────────────────

class DefaultHttpClient : public IHttpClient {
public:
    DefaultHttpClient(
        const std::string&    base_url,
        const TLSConfig&      tls,
        const TimeoutConfig&  timeouts,
        const ConnectionConfig& config = {}
    );
    ~DefaultHttpClient() override = default;

    DefaultHttpClient(const DefaultHttpClient&)            = delete;
    DefaultHttpClient& operator=(const DefaultHttpClient&) = delete;
    DefaultHttpClient(DefaultHttpClient&&)                 = default;

    RawHttpResponse request(
        const std::string&                        method,
        const std::string&                        path,
        const std::map<std::string, std::string>& headers = {},
        const std::optional<std::string>&         body    = std::nullopt
    ) override;

    RawHttpResponse request_multipart(
        const std::string&                                    path,
        const std::map<std::string, std::string>&             headers,
        const std::map<std::string, std::string>&             fields,
        const std::map<std::string, std::vector<uint8_t>>&   files = {}
    ) override;

    const std::string& base_url() const override { return base_url_; }

private:
    std::string   base_url_;
    TLSConfig     tls_;
    TimeoutConfig timeouts_;
    int           retry_count_;
    std::vector<int> retry_status_codes_;
    double        retry_delay_sec_;

    RawHttpResponse execute_once(
        const std::string&                        method,
        const std::string&                        path,
        const std::map<std::string, std::string>& headers,
        const std::optional<std::string>&         body
    );
};

// ── Test double ───────────────────────────────────────────────────────────────

class MockHttpClient : public IHttpClient {
public:
    explicit MockHttpClient(const std::string& base_url = "mock://localhost");
    ~MockHttpClient() override = default;

    // Register a canned response for (METHOD, path).
    // METHOD should be uppercase e.g. "GET", "POST".
    void register_response(
        const std::string& method,
        const std::string& path,
        RawHttpResponse    response
    );

    RawHttpResponse request(
        const std::string&                        method,
        const std::string&                        path,
        const std::map<std::string, std::string>& headers = {},
        const std::optional<std::string>&         body    = std::nullopt
    ) override;

    RawHttpResponse request_multipart(
        const std::string&                                    path,
        const std::map<std::string, std::string>&             headers,
        const std::map<std::string, std::string>&             fields,
        const std::map<std::string, std::vector<uint8_t>>&   files = {}
    ) override;

    const std::string& base_url() const override { return base_url_; }

    // Expose recorded calls for assertions
    struct RecordedCall {
        std::string method;
        std::string path;
    };
    const std::vector<RecordedCall>& recorded_calls() const { return calls_; }

private:
    std::string base_url_;
    std::map<std::pair<std::string, std::string>, RawHttpResponse> responses_;
    std::vector<RecordedCall> calls_;
};

// Legacy alias — keeps old code compiling during migration
using HttpClient = DefaultHttpClient;

} // namespace redfish

