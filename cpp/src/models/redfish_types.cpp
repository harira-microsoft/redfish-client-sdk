/**
 * src/models/redfish_types.cpp
 *
 * Implements parse_sel_entry() — FR6.6 SEL parsing.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/errors.hpp"
#include <algorithm>
#include <cctype>
#include <stdexcept>

namespace redfish {

static const char SEL_PREFIX[] = "Raw Data : Hex ";
constexpr uint8_t SEL_TYPE_PXE     = 0xCA;
constexpr uint8_t SEL_TYPE_HOST_OS = 0xD9;

ParsedSelRecord parse_sel_entry(const std::string& raw_hex) {
    std::string hex = raw_hex;

    // Strip OpenBMC prefix: "Raw Data : Hex <hex>"
    const std::string prefix(SEL_PREFIX);
    if (hex.size() >= prefix.size() &&
        hex.substr(0, prefix.size()) == prefix) {
        hex = hex.substr(prefix.size());
    } else {
        // Strip flat generator prefix: "Raw data: <hex>" (case-insensitive, FR6.6 v0.3)
        // Handles "Raw data: 91 06 02 ..." emitted by SELRawText replay tools
        std::string lower_hex = hex;
        std::transform(lower_hex.begin(), lower_hex.end(), lower_hex.begin(),
                        [](unsigned char c){ return static_cast<unsigned char>(std::tolower(c)); });
        const std::string flat_prefix = "raw data:";
        if (lower_hex.size() >= flat_prefix.size() &&
            lower_hex.substr(0, flat_prefix.size()) == flat_prefix) {
            hex = hex.substr(flat_prefix.size());
            // trim leading whitespace
            auto start = hex.find_first_not_of(" \t");
            hex = (start == std::string::npos) ? "" : hex.substr(start);
        }
    }

    // Strip spaces
    hex.erase(std::remove_if(hex.begin(), hex.end(),
        [](unsigned char c){ return std::isspace(c); }), hex.end());

    if (hex.size() < 32)
        throw RedfishSDKError("SEL record too short: " + std::to_string(hex.size())
                              + " hex chars (need >= 32 for 16 bytes)");

    // Validate hex and decode first 16 bytes
    std::vector<uint8_t> bytes;
    bytes.reserve(16);
    for (size_t i = 0; i < 32; i += 2) {
        std::string byte_str = hex.substr(i, 2);
        try {
            bytes.push_back(static_cast<uint8_t>(std::stoul(byte_str, nullptr, 16)));
        } catch (...) {
            throw RedfishSDKError("Invalid hex in SEL record at position " + std::to_string(i));
        }
    }

    // Timestamp: bytes[3..6] little-endian uint32
    uint32_t ts = static_cast<uint32_t>(bytes[3])
                | (static_cast<uint32_t>(bytes[4]) << 8)
                | (static_cast<uint32_t>(bytes[5]) << 16)
                | (static_cast<uint32_t>(bytes[6]) << 24);

    std::string record_type;
    if (bytes[0] == SEL_TYPE_PXE) {
        record_type = "PxeBoot";
    } else if (bytes[0] == SEL_TYPE_HOST_OS) {
        if      (bytes[13] == 0x01) record_type = "HostOsModeChange";
        else if (bytes[13] == 0x02) record_type = "HostOsHandOff";
        else                        record_type = "Unknown";
    } else {
        record_type = "Unknown";
    }

    return ParsedSelRecord{ record_type, ts, hex.substr(0, 32) };
}

} // namespace redfish

