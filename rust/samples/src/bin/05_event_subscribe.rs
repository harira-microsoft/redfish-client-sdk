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
    let events = ctx.event_service();
    let destination = "http://YOUR_LISTENER_HOST:9090/events";

    println!("Creating subscription -> {destination}");
    let sub_resp = events.subscribe(
        destination,
        vec!["Alert".into(), "ResourceUpdated".into(), "StatusChange".into()],
        vec![],
        vec![],
        vec![],
        None,
        Some("RSDK-Sample-05"),
        "Redfish",
        "RedfishEvent",
    ).await?;

    let sub_uri: Option<String> = if sub_resp.success {
        let uri = sub_resp.body.as_ref()
            .and_then(|b| b["@odata.id"].as_str()).map(str::to_string);
        println!("  Subscribed - URI: {}", uri.as_deref().unwrap_or("?"));
        uri
    } else {
        println!("  Subscribe failed: HTTP {}", sub_resp.status_code);
        None
    };

    println!("\nListing subscriptions ...");
    let lr = events.list_subscriptions().await?;
    if lr.success {
        let n = lr.body.as_ref().and_then(|b| b["Members"].as_array()).map(|a| a.len()).unwrap_or(0);
        println!("  Total: {n}");
    }

    if let Some(ref uri) = sub_uri {
        println!("\nFetching subscription: {uri}");
        let gr = events.get_subscription(uri).await?;
        if gr.success {
            if let Some(b) = &gr.body {
                println!("  Destination : {}", b["Destination"].as_str().unwrap_or("?"));
                println!("  Context     : {}", b["Context"].as_str().unwrap_or("?"));
            }
        }
    }

    println!("\nSubmitting test event ...");
    let tr = events.submit_test_event(serde_json::json!({})).await?;
    if tr.success {
        println!("  Test event submitted");
    } else {
        println!("  HTTP {} (may not be supported)", tr.status_code);
    }

    if let Some(ref uri) = sub_uri {
        let dr = events.delete_subscription(uri).await?;
        if dr.success {
            println!("  Subscription deleted");
        }
    }

    println!("\nEvent subscription sample complete");
    Ok(())
}
