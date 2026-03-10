// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use redfish_sdk::services::log_service::LogServiceHandle;

static SAMPLES: &[(&str, &str, &str)] = &[
    ("PXE Boot Start   ", "b70fcad117db6837010000002000FFFF", "Raw data: b7 0f ca d1 17 db 68 37 01 00 00 00 20 00 FF FF"),
    ("PXE Boot IPv4    ", "b80fca3b18db6837010002012018FFFF", "Raw data: b8 0f ca 3b 18 db 68 37 01 00 02 01 20 18 FF FF"),
    ("Unknown / Std    ", "b413024fd1dd6820000412076FC580FF", "Bad sensor reading"),
    ("Normal entry     ", "12345", "Memory ECC error detected on DIMM_A1"),
];

fn main() {
    println!("{:<20}  parsed", "Label");
    println!("{}", "-".repeat(60));

    let mut ok = 0u32;
    let mut errs = 0u32;
    for (label, _hex, message_text) in SAMPLES {
        // Build a minimal JSON LogEntry to feed into parse_sel_entry
        let entry = serde_json::json!({
            "Id": "1",
            "Created": "2024-01-15T10:30:00Z",
            "MessageId": "Base.1.0.GeneralError",
            "Severity": "Warning",
            "Message": message_text,
        });
        match LogServiceHandle::parse_sel_entry(&entry) {
            Some(sel) => {
                ok += 1;
                println!("{label:<20}  msg={:?}  raw_bytes={}", sel.message, sel.raw_bytes.is_some());
            }
            None => {
                errs += 1;
                println!("{label:<20}  None returned");
            }
        }
    }

    println!("\nParsed {ok} records OK, {errs} None returns");

    println!("\nError handling: parse_sel_entry never errors - returns None for unknown formats");
    let empty = serde_json::json!({});
    let result = LogServiceHandle::parse_sel_entry(&empty);
    println!("  Empty entry -> {:?}", result.is_some());
}
