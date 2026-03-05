"""
Sample 14 — SEL (System Event Log) binary record parsing (FR6.6)

Demonstrates parse_sel_entry() using real production hex strings from
OpenBMC event logs (LogEntry.MessageArgs[0] format).

No live BMC or simulator required — this is pure logic.

Run:
  cd python
  python samples/14_sel_parsing.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redfish_sdk import parse_sel_entry, ParsedSelRecord

# Real production SEL records from OpenBMC (MessageArgs[0] / "Raw Data : Hex " format)
SAMPLES = [
    # (label, hex_string)
    ("PXE Boot Start   ", "b70fcad117db6837010000002000FFFF"),
    ("PXE Boot IPv4    ", "b80fca3b18db6837010002012018FFFF"),
    ("PXE Boot IPv6    ", "bc0fca7c18db6837010002022016FFFF"),
    ("HostOS ModeChange", "e911d9df4cdc682000000401 01 01 0200"),
    ("HostOS HandOff   ", "0c12d9b14ddc68200000040101020200"),
    ("Unknown / Std    ", "b413024fd1dd6820000412076FC580FF"),
    # With the OpenBMC 'Raw Data : Hex' prefix
    ("PXE (with prefix)", "Raw Data : Hex b70fcad117db6837010000002000FFFF"),
]


def main() -> None:
    print(f"{'Label':<20}  {'record_type':<20}  {'record_id':>8}  {'timestamp_raw':>14}  description")
    print("-" * 90)
    ok = err = 0
    for label, hex_str in SAMPLES:
        try:
            rec: ParsedSelRecord = parse_sel_entry(hex_str)
            print(
                f"{label:<20}  {rec.record_type:<20}  "
                f"0x{rec.record_id:04X}  {rec.timestamp_raw:>14}  {rec.description}"
            )
            ok += 1
        except Exception as exc:
            print(f"{label:<20}  ERROR: {exc}")
            err += 1

    print()
    print(f"Parsed {ok} records OK, {err} errors")

    # Also demonstrate error handling
    print("\nError handling examples:")
    bad_cases = [
        ("Too short",    "AABB"),
        ("Invalid hex",  "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"),
    ]
    from redfish_sdk.errors import RedfishSDKError
    for label, bad_hex in bad_cases:
        try:
            parse_sel_entry(bad_hex)
            print(f"  {label}: UNEXPECTEDLY passed")
        except RedfishSDKError as exc:
            print(f"  {label}: correctly raised RedfishSDKError — {exc}")


if __name__ == "__main__":
    main()
