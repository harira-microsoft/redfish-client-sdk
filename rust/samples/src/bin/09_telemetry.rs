// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError};

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
    let tel = ctx.telemetry_service();

    println!("Listing metric report definitions ...");
    let dr = tel.list_metric_report_definitions().await?;
    if dr.success {
        let n = dr.body.as_ref().and_then(|b| b["Members"].as_array()).map(|a| a.len()).unwrap_or(0);
        println!("  Count: {n}");
        if let Some(arr) = dr.body.as_ref().and_then(|b| b["Members"].as_array()) {
            for d in arr.iter().take(5) { println!("    {}", d["@odata.id"].as_str().unwrap_or("?")); }
        }
    }

    println!("\nListing metric reports ...");
    let rr = tel.list_metric_reports().await?;
    if !rr.success {
        println!("  HTTP {} - TelemetryService may not be present", rr.status_code);
        println!("\nTelemetry sample complete (limited)");
        return Ok(());
    }

    let report_uris: Vec<String> = rr.body.as_ref()
        .and_then(|b| b["Members"].as_array())
        .map(|a| a.iter().filter_map(|v| v["@odata.id"].as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    println!("  Count: {}", report_uris.len());
    for u in report_uris.iter().take(5) { println!("    {u}"); }

    if let Some(uri) = report_uris.first() {
        println!("\nFetching report: {uri}");
        let rep = tel.get_metric_report(uri).await?;
        if rep.success {
            if let Some(b) = &rep.body {
                println!("  Name      : {}", b["Name"].as_str().unwrap_or("?"));
                println!("  Timestamp : {}", b["Timestamp"].as_str().unwrap_or("?"));
                if let Some(vals) = b["MetricValues"].as_array() {
                    println!("  MetricValues: {} value(s)", vals.len());
                    for mv in vals.iter().take(5) {
                        println!("    {} = {}", mv["MetricId"].as_str().unwrap_or("?"), mv["MetricValue"]);
                    }
                }
            }
        }
    }
    println!("\nTelemetry sample complete");
    Ok(())
}
