// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use std::time::Instant;
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

async fn run_mode(label: &str, host: &str, port: u16, user: &str, password: &str,
    mode: AuthMode, config: ConnectionConfig) -> Result<(), RedfishError> {
    println!("\n{}\n  {label}\n{}", "=".repeat(60), "=".repeat(60));
    let t0 = Instant::now();
    let ctx = match connect(host, port, Credentials::new(user, password), mode, config).await {
        Ok(c) => c,
        Err(e) => { println!("  Connect failed: {e}"); return Ok(()); }
    };
    println!("  Connected in {:.1}ms", t0.elapsed().as_secs_f64() * 1000.0);
    let caps = ctx.capabilities();
    println!("  RedfishVersion : {}", caps.redfish_version);

    let t0 = Instant::now();
    let r = ctx.get("/redfish/v1/Systems").await?;
    let icon = if r.success { "OK" } else { "FAIL" };
    println!("  [{icon}] GET /redfish/v1/Systems -> {}  ({:.1}ms)", r.status_code, t0.elapsed().as_secs_f64()*1000.0);

    for _ in 0..3 {
        let t0 = Instant::now();
        let r = ctx.get("/redfish/v1").await?;
        println!("  GET /redfish/v1 -> {}  ({:.1}ms)", r.status_code, t0.elapsed().as_secs_f64()*1000.0);
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls) = parse_args();
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let config = ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() };

    run_mode("AuthMode::SESSION", &host, port, &user, &password, AuthMode::Session, config.clone()).await?;
    run_mode("AuthMode::STATELESS", &host, port, &user, &password, AuthMode::Stateless, config.clone()).await?;

    println!("\n-- Bad credentials demo --");
    match connect(&host, port, Credentials::new("wrong","wrong"), AuthMode::Session, config).await {
        Err(e) => println!("  RedfishError raised as expected: {e}"),
        Ok(_)  => println!("  (Endpoint accepted bad credentials)"),
    }

    println!("\nSession vs stateless comparison complete");
    Ok(())
}
