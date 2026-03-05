//! Sample 01 - Connect and perform full service discovery.
//!
//! Demonstrates:
//!   - `redfish_sdk::connect()`
//!   - Full discovery via `ClientContext::discovery().full()`
//!   - Inspecting `DiscoveryResult`
//!
//! Usage:
//!   cargo run --bin 01_connect_discover -- --host 127.0.0.1 --port 8000

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
    let creds = Credentials::new(&user, &password);
    let config = ConnectionConfig { verify_tls: !no_tls, ..Default::default() };

    println!("Connecting to {host}:{port} ...");

    let ctx = connect(&host, port, creds, AuthMode::Session, config).await
        .map_err(|e| { eprintln!("[ERROR] Connection failed: {e}"); e })?;

    println!("Connected\n");

    // Full discovery
    println!("Running full service discovery ...");
    let result = ctx.discovery().full().await?;

    println!("\n{:<30} {}", "Service", "URI");
    println!("{}", "-".repeat(70));
    for (name, uri) in &result.services {
        println!("  {name:<28} {uri}");
    }

    // Capabilities
    let caps = ctx.capabilities();
    println!("\nCapabilities:");
    println!("  redfish_version : {}", caps.redfish_version);
    println!("  has_systems     : {}", result.has_service("Systems"));
    println!("  has_chassis     : {}", result.has_service("Chassis"));
    println!("  has_managers    : {}", result.has_service("Managers"));
    println!("  has_events      : {}", result.has_service("EventService"));
    println!("  has_tasks       : {}", result.has_service("Tasks"));

    println!("\nDiscovery complete");
    Ok(())
}
