/**
 * src/transport/http_client.cpp
 *
 * libcurl-backed HTTP client.
 */

#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/errors.hpp"
#include <curl/curl.h>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <stdexcept>

namespace redfish {

namespace {

// libcurl write callback — appends to a std::string
static size_t write_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* buf = reinterpret_cast<std::string*>(userdata);
    buf->append(ptr, size * nmemb);
    return size * nmemb;
}

// libcurl header callback — appends raw header lines to a string
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
        if (first) { first = false; continue; } // skip HTTP/x.x status line
        if (line == "\r" || line.empty()) continue;
        auto colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::string key = line.substr(0, colon);
        std::string val = line.substr(colon + 1);
        // trim
        while (!val.empty() && (val.front() == ' ' || val.front() == '\t')) val.erase(0,1);
        while (!val.empty() && (val.back()  == '\r' || val.back()  == '\n')) val.pop_back();
        // lowercase key
        std::transform(key.begin(), key.end(), key.begin(),
                       [](unsigned char c){ return std::tolower(c); });
        result[key] = val;
    }
    return result;
}

} // anonymous namespace

// Global curl init (once per process)
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

HttpClient::HttpClient(
    const std::string&   base_url,
    const TLSConfig&     tls,
    const TimeoutConfig& timeouts
)
    : base_url_(base_url), tls_(tls), timeouts_(timeouts)
{}

HttpClient::~HttpClient() = default;

RawHttpResponse HttpClient::request(
    const std::string&                         method,
    const std::string&                         path,
    const std::map<std::string, std::string>&  extra_headers,
    const std::optional<std::string>&          body
) {
    CURL* curl = curl_easy_init();
    if (!curl) throw RedfishConnectionError("curl_easy_init() failed");

    std::string url = base_url_ + path;
    std::string response_body;
    std::string response_headers;

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &response_body);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, header_cb);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA,     &response_headers);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, timeouts_.connect_sec);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT,        timeouts_.request_sec);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);

    // TLS
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

    // Merge headers: Redfish defaults + caller-supplied
    struct curl_slist* hlist = nullptr;
    auto merged = REDFISH_HEADERS;
    for (auto& [k, v] : extra_headers) merged[k] = v;
    for (auto& [k, v] : merged) {
        std::string h = k + ": " + v;
        hlist = curl_slist_append(hlist, h.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hlist);

    // Method + body
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
    if (res == CURLE_OK)
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_slist_free_all(hlist);
    curl_easy_cleanup(curl);

    if (res == CURLE_OPERATION_TIMEDOUT)
        throw RedfishTimeoutError("Request timed out: " + url);
    if (res == CURLE_COULDNT_CONNECT || res == CURLE_COULDNT_RESOLVE_HOST)
        throw RedfishConnectionError("Cannot reach " + url + ": " + curl_easy_strerror(res));
    if (res == CURLE_SSL_CONNECT_ERROR || res == CURLE_PEER_FAILED_VERIFICATION)
        throw RedfishTLSError("TLS error: " + std::string(curl_easy_strerror(res)));
    if (res != CURLE_OK)
        throw RedfishConnectionError("curl error " + std::to_string(res) + ": " + curl_easy_strerror(res));

    RawHttpResponse raw;
    raw.status_code   = static_cast<int>(http_code);
    raw.headers       = parse_headers(response_headers);
    raw.body_text     = response_body;
    raw.is_json       = !response_body.empty();  // refined by caller
    raw.body_json_str = response_body;
    return raw;
}

} // namespace redfish
