// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use redfish_sdk::{connect_blocking, AuthMode, ConnectionConfig, Credentials, RedfishError};

fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let creds = Credentials::new("admin", "password");
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let config = ConnectionConfig {
        verify_tls: false,
        use_tls: !no_tls_proto,
        retry_on_connection_failure: 2,
        retry_status_codes: vec![503, 429],
        retry_delay_secs: 1,
        ..Default::default()
    };

    println!("Connecting with retry config (retry=2, status_codes=[503,429]) ...");
    let mut ctx = connect_blocking("127.0.0.1", 8000, creds, AuthMode::Stateless, config)
        .map_err(|e| { eprintln!("[ERROR] {e}"); e })?;
    println!("Connected");
    println!("  Redfish version : {}", ctx.capabilities().redfish_version);

    println!("\nRefreshing auth ...");
    ctx.refresh_auth_blocking()?;
    println!("  Auth refreshed");

    let root = ctx.get_blocking("/redfish/v1")?;
    println!("  GET /redfish/v1 -> HTTP {}", root.status_code);

    println!("\nDone.");
    Ok(())
}
