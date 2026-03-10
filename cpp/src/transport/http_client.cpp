// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/transport/http_client.cpp
 *
 * Transport layer — v0.2
 *   DefaultHttpClient : libcurl, retry loop (FR1.8, FR1.9), multipart (FR7.5)
 *   MockHttpClient    : canned responses for unit tests (NFR8.2)
 */

#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/errors.hpp"
#include "../internal/logger.hpp"
#include <curl/curl.h>
#include <algorithm>
#include <cctype>
#include <chrono>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace redfish {

namespace {

static size_t write_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* buf = reinterpret_cast<std::string*>(userdata);
    buf->append(ptr, size * nmemb);
    return size * nmemb;
}

static size_t header_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* buf = reinterpret_cast<std::string*>(userdata);
    buf->append(ptr, size * nmemb);
    return size * nmemb;
}

std::map<std::string, std::string> parse_headers(const std::string& raw) {
    std::map<std::string, std::string> result;
    std::istringstream ss(raw);
    std::string line;
    bool first = true;
    while (std::getline(ss, line)) {
        if (first) { first = false; continue; }
        if (line == "\r" || line.empty()) continue;
        auto colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::string key = line.substr(0, colon);
        std::string val = line.substr(colon + 1);
        while (!val.empty() && (val.front() == ' ' || val.front() == '\t')) val.erase(0, 1);
        while (!val.empty() && (val.back() == '\r' || val.back() == '\n')) val.pop_back();
        std::transform(key.begin(), key.end(), key.begin(),
                       [](unsigned char c){ return std::tolower(c); });
        result[key] = val;
    }
    return result;
}

bool is_ssl_error(CURLcode res) {
    return res == CURLE_SSL_CONNECT_ERROR
        || res == CURLE_PEER_FAILED_VERIFICATION
        || res == CURLE_SSL_CERTPROBLEM
        || res == CURLE_SSL_CIPHER
        || res == CURLE_SSL_CACERT
        || res == CURLE_SSL_CACERT_BADFILE;
}

} // anonymous namespace

// ── Global curl init ──────────────────────────────────────────────────────────

struct CurlGlobalInit {
    CurlGlobalInit()  { curl_global_init(CURL_GLOBAL_ALL); }
    ~CurlGlobalInit() { curl_global_cleanup(); }
};
static CurlGlobalInit _curl_global;

static const std::map<std::string, std::string> REDFISH_HEADERS = {
    {"OData-Version", "4.0"},
    {"Content-Type",  "application/json"},
    {"Accept",        "application/json"},
};

// ── DefaultHttpClient ─────────────────────────────────────────────────────────

DefaultHttpClient::DefaultHttpClient(
    const std::string&    base_url,
    const TLSConfig&      tls,
    const TimeoutConfig&  timeouts,
    const ConnectionConfig& config
)
    : base_url_(base_url)
    , tls_(tls)
    , timeouts_(timeouts)
    , retry_count_(std::max(0, config.retry_on_connection_failure))
    , retry_status_codes_(config.retry_status_codes)
    , retry_delay_sec_(config.retry_delay_sec)
{}

RawHttpResponse DefaultHttpClient::execute_once(
    const std::string&                        method,
    const std::string&                        path,
    const std::map<std::string, std::string>& extra_headers,
    const std::optional<std::string>&         body
) {
    CURL* curl = curl_easy_init();
    if (!curl) throw RedfishConnectionError("curl_easy_init() failed");

    std::string url = base_url_ + path;
    std::string response_body;
    std::string response_headers_raw;

    curl_easy_setopt(curl, CURLOPT_URL,            url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &response_body);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, header_cb);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA,     &response_headers_raw);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, timeouts_.connect_sec);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        timeouts_.request_sec);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);

    if (!tls_.verify) {
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
    }
    if (!tls_.ca_cert.empty())
        curl_easy_setopt(curl, CURLOPT_CAINFO, tls_.ca_cert.c_str());
    if (!tls_.client_cert.empty())
        curl_easy_setopt(curl, CURLOPT_SSLCERT, tls_.client_cert.c_str());
    if (!tls_.client_key.empty())
        curl_easy_setopt(curl, CURLOPT_SSLKEY, tls_.client_key.c_str());

    auto merged = REDFISH_HEADERS;
    for (auto& [k, v] : extra_headers) merged[k] = v;
    struct curl_slist* hlist = nullptr;
    for (auto& [k, v] : merged) {
        std::string h = k + ": " + v;
        hlist = curl_slist_append(hlist, h.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hlist);

    if (method == "GET") {
        curl_easy_setopt(curl, CURLOPT_HTTPGET, 1L);
    } else if (method == "POST") {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        if (body) {
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS,    body->c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, (long)body->size());
        } else {
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS,    "");
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, 0L);
        }
    } else if (method == "PATCH" || method == "PUT" || method == "DELETE") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, method.c_str());
        if (body) {
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS,    body->c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, (long)body->size());
        }
    }

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    // Always attempt to read the HTTP code — valid even for partial transfers (e.g. CURLE_RECV_ERROR)
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_slist_free_all(hlist);
    curl_easy_cleanup(curl);

    if (res == CURLE_OPERATION_TIMEDOUT)
        throw RedfishTimeoutError("Request timed out: " + url);
    if (is_ssl_error(res))
        throw RedfishTLSError("TLS error: " + std::string(curl_easy_strerror(res)));
    if (res == CURLE_COULDNT_CONNECT || res == CURLE_COULDNT_RESOLVE_HOST)
        throw RedfishConnectionError("Cannot reach " + url + ": " + curl_easy_strerror(res));
    // CURLE_RECV_ERROR (56): server closed connection after sending headers/body.
    // If we got an HTTP code, treat it as a valid (possibly partial) response.
    if (res == CURLE_RECV_ERROR && http_code > 0) {
        // fall through to build RawHttpResponse below
    } else if (res != CURLE_OK) {
        throw RedfishConnectionError("curl error " + std::to_string(res) + ": " + curl_easy_strerror(res));
    }

    RawHttpResponse raw;
    raw.status_code   = static_cast<int>(http_code);
    raw.headers       = parse_headers(response_headers_raw);
    raw.body_text     = response_body;
    raw.is_json       = !response_body.empty();
    raw.body_json_str = response_body;
    return raw;
}

RawHttpResponse DefaultHttpClient::request(
    const std::string&                        method,
    const std::string&                        path,
    const std::map<std::string, std::string>& headers,
    const std::optional<std::string>&         body
) {
    int max_attempts = retry_count_ + 1;
    std::exception_ptr last_exc = nullptr;
    RawHttpResponse    last_resp;

    for (int attempt = 0; attempt < max_attempts; ++attempt) {
        if (attempt > 0) {
            REDFISH_LOG_DEBUG("http_client",
                "Retry " + std::to_string(attempt) + "/" + std::to_string(retry_count_)
                + " for " + method + " " + path
                + " after " + std::to_string(retry_delay_sec_) + "s");
            std::this_thread::sleep_for(
                std::chrono::milliseconds(static_cast<int>(retry_delay_sec_ * 1000)));
        }

        try {
            auto raw = execute_once(method, path, headers, body);
            bool retryable = false;
            for (int code : retry_status_codes_) {
                if (raw.status_code == code && attempt < retry_count_) {
                    retryable = true;
                    break;
                }
            }
            if (retryable) {
                REDFISH_LOG_DEBUG("http_client",
                    "HTTP " + std::to_string(raw.status_code) + " in retry_status_codes; retrying");
                last_resp = raw;
                continue;
            }
            REDFISH_LOG_DEBUG("http_client",
                method + " " + path + " -> HTTP " + std::to_string(raw.status_code));
            return raw;
        } catch (const RedfishTLSError&) {
            // TLS errors must not be retried
            throw;
        } catch (const RedfishConnectionError& e) {
            REDFISH_LOG_WARNING("http_client",
                "Connection attempt " + std::to_string(attempt + 1)
                + "/" + std::to_string(max_attempts) + " failed: " + e.what());
            last_exc = std::current_exception();
        }
    }

    if (last_exc) {
        REDFISH_LOG_ERROR("http_client",
            "All " + std::to_string(max_attempts) + " attempt(s) failed for "
            + method + " " + path);
        std::rethrow_exception(last_exc);
    }
    return last_resp;
}

RawHttpResponse DefaultHttpClient::request_multipart(
    const std::string&                                  path,
    const std::map<std::string, std::string>&           headers,
    const std::map<std::string, std::string>&           fields,
    const std::map<std::string, std::vector<uint8_t>>& files
) {
    CURL* curl = curl_easy_init();
    if (!curl) throw RedfishConnectionError("curl_easy_init() failed");

    std::string url = base_url_ + path;
    std::string response_body;
    std::string response_headers_raw;

    curl_easy_setopt(curl, CURLOPT_URL,            url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &response_body);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, header_cb);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA,     &response_headers_raw);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, timeouts_.connect_sec);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        timeouts_.request_sec);

    if (!tls_.verify) {
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
    }
    if (!tls_.ca_cert.empty())
        curl_easy_setopt(curl, CURLOPT_CAINFO, tls_.ca_cert.c_str());

    // Auth and OData headers only (no Content-Type — curl sets multipart boundary)
    struct curl_slist* hlist = nullptr;
    hlist = curl_slist_append(hlist, "OData-Version: 4.0");
    hlist = curl_slist_append(hlist, "Accept: application/json");
    for (auto& [k, v] : headers) {
        std::string h = k + ": " + v;
        hlist = curl_slist_append(hlist, h.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hlist);

    curl_mime* mime = curl_mime_init(curl);

    for (auto& [name, value] : fields) {
        curl_mimepart* part = curl_mime_addpart(mime);
        curl_mime_name(part, name.c_str());
        curl_mime_data(part, value.c_str(), CURL_ZERO_TERMINATED);
        curl_mime_type(part, "application/json");
    }
    for (auto& [name, data] : files) {
        curl_mimepart* part = curl_mime_addpart(mime);
        curl_mime_name(part, name.c_str());
        curl_mime_data(part, reinterpret_cast<const char*>(data.data()), data.size());
        curl_mime_filename(part, name.c_str());
        curl_mime_type(part, "application/octet-stream");
    }

    curl_easy_setopt(curl, CURLOPT_MIMEPOST, mime);

    CURLcode res = curl_easy_perform(curl);
    long http_code = 0;
    if (res == CURLE_OK)
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_mime_free(mime);
    curl_slist_free_all(hlist);
    curl_easy_cleanup(curl);

    if (res == CURLE_OPERATION_TIMEDOUT)
        throw RedfishTimeoutError("Multipart request timed out: " + url);
    if (is_ssl_error(res))
        throw RedfishTLSError("TLS error: " + std::string(curl_easy_strerror(res)));
    if (res != CURLE_OK)
        throw RedfishConnectionError("curl error " + std::to_string(res) + ": " + curl_easy_strerror(res));

    REDFISH_LOG_DEBUG("http_client",
        "POST (multipart) " + path + " -> HTTP " + std::to_string(http_code));

    RawHttpResponse raw;
    raw.status_code   = static_cast<int>(http_code);
    raw.headers       = parse_headers(response_headers_raw);
    raw.body_text     = response_body;
    raw.is_json       = !response_body.empty();
    raw.body_json_str = response_body;
    return raw;
}

// ── MockHttpClient ────────────────────────────────────────────────────────────

MockHttpClient::MockHttpClient(const std::string& base_url)
    : base_url_(base_url)
{}

void MockHttpClient::register_response(
    const std::string& method,
    const std::string& path,
    RawHttpResponse    response
) {
    std::string m = method;
    std::transform(m.begin(), m.end(), m.begin(),
                   [](unsigned char c){ return std::toupper(c); });
    responses_[{m, path}] = std::move(response);
}

RawHttpResponse MockHttpClient::request(
    const std::string&                        method,
    const std::string&                        path,
    const std::map<std::string, std::string>& /*headers*/,
    const std::optional<std::string>&         /*body*/
) {
    std::string m = method;
    std::transform(m.begin(), m.end(), m.begin(),
                   [](unsigned char c){ return std::toupper(c); });
    calls_.push_back({m, path});

    auto it = responses_.find({m, path});
    if (it != responses_.end()) return it->second;

    // 404 for unregistered paths
    RawHttpResponse r;
    r.status_code   = 404;
    r.body_text     = "{\"error\":{\"message\":\"MockHttpClient: no response registered for "
                      + m + " " + path + "\"}}";
    r.body_json_str = r.body_text;
    r.is_json       = true;
    return r;
}

RawHttpResponse MockHttpClient::request_multipart(
    const std::string&                                    path,
    const std::map<std::string, std::string>&             /*headers*/,
    const std::map<std::string, std::string>&             /*fields*/,
    const std::map<std::string, std::vector<uint8_t>>&   /*files*/
) {
    calls_.push_back({"POST_MULTIPART", path});
    auto it = responses_.find({"POST", path});
    if (it != responses_.end()) return it->second;

    RawHttpResponse r;
    r.status_code   = 404;
    r.body_text     = "{\"error\":{\"message\":\"MockHttpClient: no multipart response for " + path + "\"}}";
    r.body_json_str = r.body_text;
    r.is_json       = true;
    return r;
}

} // namespace redfish
