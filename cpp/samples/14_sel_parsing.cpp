/**
 * Sample 14 — SEL Parsing (v0.2)
 *
 * Demonstrates:
 *   - redfish::parse_sel_entry()  (FR6.6)
 *   - ParsedSelRecord fields
 *   - Pure logic — no network required
 *
 * Usage:
 *   ./14_sel_parsing
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/errors.hpp"
#include <iostream>
#include <string>
#include <vector>

int main() {
    struct TestCase {
        std::string description;
        std::string raw_hex;
        std::string expected_type;
    };

    std::vector<TestCase> cases = {
        {
            "PxeBoot start",
            "ca000100ac9bb24e000000000000000000000000",
            "PxeBoot"
        },
        {
            "PxeBoot IPv4",
            "ca000100b6a3b24e000004000000000000000000",
            "PxeBoot"
        },
        {
            "PxeBoot with OpenBMC prefix",
            "Raw Data : Hex ca000100c8abb24e000004000000000000000000",
            "PxeBoot"
        },
        {
            "HostOsModeChange",
            "e911d9df4cdc682000000401 01 01 0200",
            "HostOsModeChange"
        },
        {
            "HostOsHandOff",
            "0c12d9b14ddc68200000040101020200",
            "HostOsHandOff"
        },
        {
            "Unknown record type",
            "ab000100ac9bb24e000000000000000000000000",
            "Unknown"
        },
    };

    int passed = 0;
    for (auto& tc : cases) {
        try {
            auto rec = redfish::parse_sel_entry(tc.raw_hex);
            bool ok = (rec.record_type == tc.expected_type);
            std::cout << (ok ? "  PASS" : "  FAIL")
                      << "  [" << tc.description << "]\n"
                      << "       record_type=" << rec.record_type
                      << "  timestamp=" << rec.timestamp << "\n";
            if (ok) ++passed;
        } catch (const std::exception& e) {
            std::cout << "  FAIL  [" << tc.description << "] threw: " << e.what() << "\n";
        }
    }

    std::cout << "\nError handling:\n";

    // Too short
    try {
        redfish::parse_sel_entry("ca0001");
        std::cout << "  FAIL  Too short: should have thrown\n";
    } catch (const std::exception& e) {
        std::cout << "  PASS  Too short: " << e.what() << "\n";
        ++passed;
    }

    // Invalid hex
    try {
        redfish::parse_sel_entry("ca000100ac9bb24e0000000000000000GG000000");
        std::cout << "  FAIL  Invalid hex: should have thrown\n";
    } catch (const std::exception& e) {
        std::cout << "  PASS  Invalid hex: " << e.what() << "\n";
        ++passed;
    }

    int total = static_cast<int>(cases.size()) + 2;
    std::cout << "\nPassed " << passed << "/" << total << "\n";
    if (passed == total)
        std::cout << "✓ SEL parsing sample complete\n";
    else
        std::cout << "✗ Some SEL tests failed\n";

    return (passed == total) ? 0 : 1;
}
