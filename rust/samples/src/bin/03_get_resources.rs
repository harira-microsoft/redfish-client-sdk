// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError, RedfishResponse};

fn body_str(resp: &RedfishResponse, key: &str) -> String {
    resp.body.as_ref()
        .and_then(|b| b[key].as_str())
        .unwrap_or("?").to_string()
}

fn print_members(label: &str, resp: &RedfishResponse) -> Vec<String> {
    println!("\n{}\n  {label}\n{}", "=".repeat(60), "=".repeat(60));
    if !resp.success { println!("  [WARN] HTTP {}", resp.status_code); return vec![]; }
    let uris: Vec<String> = resp.body.as_ref()
        .and_then(|b| b["Members"].as_array())
        .map(|a| a.iter().filter_map(|v| v["@odata.id"].as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    let count = resp.body.as_ref()
        .and_then(|b| b["Members@odata.count"].as_u64())
        .unwrap_or(uris.len() as u64);
    println!("  Members@odata.count : {count}");
    for u in &uris { println!("    {u}"); }
    uris
}

fn parse_args() -> (String, u16, String, String, bool) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            _ => {}
        }
    }
    (host, port, user, password, no_tls)
}


#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls) = parse_args();
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() }).await?;
    ctx.discovery().full().await?;

    let r = ctx.get("/redfish/v1/Systems").await?;
    let uris = print_members("ComputerSystemCollection", &r);
    if let Some(uri) = uris.first() {
        let r2 = ctx.get(uri).await?;
        if r2.success {
            println!("\n  First System:");
            for k in &["Id","Name","Manufacturer","Model","SerialNumber","PowerState"] {
                println!("    {k:<16}: {}", body_str(&r2, k));
            }
        }
    }

    let r = ctx.get("/redfish/v1/Chassis").await?;
    let uris = print_members("ChassisCollection", &r);
    if let Some(uri) = uris.first() {
        let r2 = ctx.get(uri).await?;
        if r2.success {
            println!("\n  First Chassis:");
            for k in &["Id","ChassisType","Manufacturer"] {
                println!("    {k:<16}: {}", body_str(&r2, k));
            }
        }
    }

    let r = ctx.get("/redfish/v1/Managers").await?;
    let uris = print_members("ManagerCollection", &r);
    if let Some(uri) = uris.first() {
        let r2 = ctx.get(uri).await?;
        if r2.success {
            println!("\n  First Manager:");
            for k in &["Id","ManagerType","FirmwareVersion"] {
                println!("    {k:<16}: {}", body_str(&r2, k));
            }
        }
    }

    println!("\nResource GET complete");
    Ok(())
}
