// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/services/ras_service.cpp
 *
 * RasServiceHandle implementation — endpoint discovery, CPER event
 * subscription, large-CPER retrieval, and CPAD submission.
 */

#include "redfish_sdk/services/ras_service.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "internal/logger.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <string>

namespace redfish {

// ---------------------------------------------------------------------------
// Minimal base64 helpers (no external dependency)
// ---------------------------------------------------------------------------

static constexpr char kB64Table[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static std::string b64_encode(const std::vector<uint8_t>& data) {
    std::string out;
    out.reserve(((data.size() + 2) / 3) * 4);
    for (size_t i = 0; i < data.size(); i += 3) {
        uint32_t b = static_cast<uint32_t>(data[i]) << 16;
        if (i + 1 < data.size()) b |= static_cast<uint32_t>(data[i + 1]) << 8;
        if (i + 2 < data.size()) b |= static_cast<uint32_t>(data[i + 2]);
        out += kB64Table[(b >> 18) & 0x3F];
        out += kB64Table[(b >> 12) & 0x3F];
        out += (i + 1 < data.size()) ? kB64Table[(b >> 6) & 0x3F] : '=';
        out += (i + 2 < data.size()) ? kB64Table[b & 0x3F]        : '=';
    }
    return out;
}

static std::vector<uint8_t> b64_decode(const std::string& encoded) {
    static const int8_t kDecTable[256] = {
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
        52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-1,-1,-1,
        -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
        15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
        -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
        41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
    };
    std::vector<uint8_t> out;
    out.reserve((encoded.size() / 4) * 3);
    uint32_t buf = 0;
    int bits = 0;
    for (unsigned char c : encoded) {
        if (c == '=' || c == '\n' || c == '\r') continue;
        int8_t val = (c < 128) ? kDecTable[c] : -1;
        if (val < 0) continue;
        buf = (buf << 6) | static_cast<uint32_t>(val);
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out.push_back(static_cast<uint8_t>((buf >> bits) & 0xFF));
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static std::string to_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

CperSeverity cper_severity_from_message_id(const std::string& message_id) {
    const std::string lower = to_lower(message_id);
    if (lower.find("platformevent") != std::string::npos) return CperSeverity::PlatformEvent;
    if (lower.find("informational")  != std::string::npos) return CperSeverity::Informational;
    if (lower.find("corrected")      != std::string::npos) return CperSeverity::Corrected;
    if (lower.find("recoverable")    != std::string::npos) return CperSeverity::Recoverable;
    if (lower.find("fatal")          != std::string::npos) return CperSeverity::Fatal;
    return CperSeverity::Unknown;
}

// ---------------------------------------------------------------------------
// CperEvent factory
// ---------------------------------------------------------------------------

CperEvent CperEvent::from_event_record(const nlohmann::json& rec) {
    CperEvent ev;
    ev.event_id   = rec.value("EventId", "");
    ev.message_id = rec.value("MessageId", "");
    ev.severity   = cper_severity_from_message_id(ev.message_id);
    ev.timestamp  = rec.value("EventTimestamp", "");

    if (rec.contains("OriginOfCondition") && rec["OriginOfCondition"].contains("@odata.id"))
        ev.origin_of_condition = rec["OriginOfCondition"]["@odata.id"].get<std::string>();

    if (rec.contains("AdditionalDataURI"))
        ev.additional_data_uri = rec["AdditionalDataURI"].get<std::string>();

    // Try to decode inline CPER from AdditionalData or Oem.CperData
    std::string raw_cper;
    if (rec.contains("AdditionalData") && rec["AdditionalData"].is_string())
        raw_cper = rec["AdditionalData"].get<std::string>();
    else if (rec.contains("Oem") && rec["Oem"].contains("CperData") &&
             rec["Oem"]["CperData"].is_string())
        raw_cper = rec["Oem"]["CperData"].get<std::string>();

    if (!raw_cper.empty()) {
        try { ev.cper_data = b64_decode(raw_cper); }
        catch (...) {}
    }

    ev.raw = rec;
    return ev;
}

// ---------------------------------------------------------------------------
// Constructor / URI helpers
// ---------------------------------------------------------------------------

RasServiceHandle::RasServiceHandle(
    IHttpClient&                              http,
    const AuthState&                          auth_state,
    const std::map<std::string, std::string>& discovery_map
)
    : http_(http)
    , auth_state_(auth_state)
    , discovery_map_(discovery_map)
{}

std::string RasServiceHandle::service_uri() const {
    auto it = discovery_map_.find("RasService");
    return (it != discovery_map_.end()) ? it->second : "/redfish/v1/RasService";
}

std::string RasServiceHandle::event_subscriptions_uri() const {
    auto it = discovery_map_.find("EventService");
    std::string base = (it != discovery_map_.end()) ? it->second : "/redfish/v1/EventService";
    return base + "/Subscriptions";
}

// ---------------------------------------------------------------------------
// Endpoint discovery
// ---------------------------------------------------------------------------

std::vector<RasEndpoint> RasServiceHandle::discover_endpoints() {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw  = http_.request("GET", service_uri(), headers);
    REDFISH_LOG_DEBUG("ras_service", "GET " + service_uri() + " -> " + std::to_string(raw.status_code));

    auto resp = build_response(raw.status_code, raw.headers, raw.body_text);
    if (!resp.success) {
        REDFISH_LOG_WARNING("ras_service", "RAS endpoint discovery failed: HTTP " +
                            std::to_string(raw.status_code));
        return {};
    }

    std::vector<RasEndpoint> endpoints;
    if (!resp.body.contains("Members") || !resp.body["Members"].is_array())
        return endpoints;

    for (const auto& member : resp.body["Members"]) {
        std::string uri = member.value("@odata.id", "");
        if (uri.empty()) continue;

        auto dr   = http_.request("GET", uri, headers);
        auto dresp = build_response(dr.status_code, dr.headers, dr.body_text);
        if (!dresp.success) continue;

        const auto& d = dresp.body;
        RasEndpoint ep;
        ep.endpoint_id  = d.value("Id", "");
        ep.creator_id   = d.value("CreatorId", "");
        ep.fru_id       = d.value("FruId", "");
        ep.partition_id = d.value("PartitionId", "");
        ep.uri          = uri;
        ep.raw          = d;
        if (d.contains("SupportedQueues") && d["SupportedQueues"].is_array())
            for (const auto& q : d["SupportedQueues"])
                ep.supported_queues.push_back(q.get<std::string>());
        endpoints.push_back(std::move(ep));
    }

    REDFISH_LOG_DEBUG("ras_service",
                      "Discovered " + std::to_string(endpoints.size()) + " RAS endpoint(s)");
    return endpoints;
}

// ---------------------------------------------------------------------------
// CPER event subscription
// ---------------------------------------------------------------------------

RedfishResponse RasServiceHandle::subscribe_cper_events(
    const std::string&              destination,
    const std::vector<std::string>& registry_prefixes,
    const std::vector<std::string>& message_ids,
    const std::string&              context,
    const std::string&              event_format_type
) {
    nlohmann::json body = {
        {"Destination",     destination},
        {"Protocol",        "Redfish"},
        {"SubscriptionType","RedfishEvent"},
        {"Context",         context},
        {"EventFormatType", event_format_type},
    };
    if (!registry_prefixes.empty()) body["RegistryPrefixes"] = registry_prefixes;
    if (!message_ids.empty())       body["MessageIds"]       = message_ids;

    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("POST", event_subscriptions_uri(), headers, body.dump());
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

// ---------------------------------------------------------------------------
// Large-CPER retrieval
// ---------------------------------------------------------------------------

std::vector<uint8_t> RasServiceHandle::fetch_cper_data(const std::string& uri) {
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw  = http_.request("GET", uri, headers);
    auto resp = build_response(raw.status_code, raw.headers, raw.body_text);

    if (!resp.success)
        throw std::runtime_error(
            "Failed to fetch CPER data from " + uri +
            ": HTTP " + std::to_string(raw.status_code));

    // Try known base64 fields in priority order
    for (const char* key : {"CperData", "Data", "AdditionalData"}) {
        if (resp.body.contains(key) && resp.body[key].is_string()) {
            try { return b64_decode(resp.body[key].get<std::string>()); }
            catch (...) {}
        }
    }

    // Fallback: serialise the JSON body as bytes
    std::string json_str = resp.body.dump();
    return std::vector<uint8_t>(json_str.begin(), json_str.end());
}

// ---------------------------------------------------------------------------
// CPAD submission
// ---------------------------------------------------------------------------

RedfishResponse RasServiceHandle::submit_cpad(
    const std::string& cpad_uri,
    const CpadRecord&  cpad
) {
    nlohmann::json body = {
        {"PlatformId",  cpad.platform_id},
        {"PartitionId", cpad.partition_id},
        {"CreatorId",   cpad.creator_id},
        {"FruId",       cpad.fru_id},
        {"FruText",     cpad.fru_text},
        {"Payload",     b64_encode(cpad.payload)},
    };
    std::map<std::string, std::string> headers;
    AuthManager::attach_auth(auth_state_, headers);
    auto raw = http_.request("PUT", cpad_uri, headers, body.dump());
    return build_response(raw.status_code, raw.headers, raw.body_text);
}

// ---------------------------------------------------------------------------
// Push-mode event parsing
// ---------------------------------------------------------------------------

std::vector<CperEvent> RasServiceHandle::parse_cper_events(
    const nlohmann::json& event_payload
) {
    std::vector<CperEvent> results;
    if (!event_payload.contains("Events") || !event_payload["Events"].is_array())
        return results;

    for (const auto& record : event_payload["Events"]) {
        CperEvent ev = CperEvent::from_event_record(record);
        std::string lower = to_lower(ev.message_id);
        if (ev.severity != CperSeverity::Unknown ||
            lower.find("cper") != std::string::npos ||
            lower.find("ras")  != std::string::npos)
        {
            results.push_back(std::move(ev));
        }
    }
    return results;
}

} // namespace redfish
