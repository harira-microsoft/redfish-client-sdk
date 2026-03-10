// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use std::io::Write;
use redfish_sdk::RedfishError;

fn temp_firmware(name: &str) -> String {
    let path = std::env::temp_dir().join(name);
    let mut f = std::fs::File::create(&path).unwrap();
    f.write_all(&[0xDE, 0xAD, 0xBE, 0xEF].repeat(256)).unwrap();
    path.to_string_lossy().into_owned()
}

fn demo_successful_upload() {
    println!("=== Scenario 1: successful multipart upload (202 expected) ===");
    let firmware_path = temp_firmware("sample15_fw.bin");
    println!("  Firmware file : {firmware_path}");
    println!("  Would call    : update_service.push_firmware(");
    println!("                      local_path = \"{firmware_path}\",");
    println!("                      targets    = [\"/redfish/v1/Systems/1/Bios\"],");
    println!("                      apply_time = \"OnReset\",");
    println!("                  )");
    println!("  Expected      : HTTP 202 + Task URI");
    std::fs::remove_file(&firmware_path).ok();
    println!("  Scenario 1 documented");
}

fn demo_no_push_uri() {
    println!("\n=== Scenario 2: no push URI -> ProtocolError ===");
    let err: RedfishError = RedfishError::ProtocolError(
        "UpdateService has no push URI (MultipartHttpPushUri / HttpPushUri absent)".to_string()
    );
    println!("  Error variant : {err}");
    println!("  Scenario 2 documented");
}

fn main() {
    demo_successful_upload();
    demo_no_push_uri();
    println!("\nDone.");
}
