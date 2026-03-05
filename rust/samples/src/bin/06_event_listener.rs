use std::{sync::{Arc, Mutex}, time::Duration};
use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError, RedfishEventListener};

fn parse_args() -> (String, u16, String, String, bool, u16, f64) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut listen_port = 9090u16;
    let mut wait = 10.0f64;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            "--listen-port"   => { listen_port = it.next().unwrap().parse().unwrap(); }
            "--wait"          => { wait = it.next().unwrap().parse().unwrap(); }
            _ => {}
        }
    }
    (host, port, user, password, no_tls, listen_port, wait)
}

#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls, listen_port, wait_secs) = parse_args();
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, ..Default::default() }).await?;

    let mut listener = RedfishEventListener::new(listen_port)
        .with_context_token("RSDK-Sample-06");

    let received: Arc<Mutex<usize>> = Arc::new(Mutex::new(0));
    let rc = Arc::clone(&received);
    listener.on_event(move |ev| {
        *rc.lock().unwrap() += 1;
        println!("  [EVENT] type={:?}  id={:?}", ev.event_type, ev.message_id);
    });

    listener.start().await?;
    println!("Listener running on 0.0.0.0:{listen_port}");

    let dest = format!("http://127.0.0.1:{listen_port}");
    let events = ctx.event_service();
    let sr = events.subscribe(
        &dest,
        vec!["Alert".into(), "ResourceUpdated".into(), "StatusChange".into()],
        vec![], vec![], vec![], None, Some("RSDK-Sample-06"), "Redfish", "RedfishEvent",
    ).await?;

    let sub_uri: Option<String> = if sr.success {
        let uri = sr.body.as_ref().and_then(|b| b["@odata.id"].as_str()).map(str::to_string);
        println!("  Subscribed - URI: {}", uri.as_deref().unwrap_or("?"));
        uri
    } else {
        println!("  Subscribe failed HTTP {}", sr.status_code);
        None
    };

    let _ = events.submit_test_event(serde_json::json!({})).await;
    println!("Waiting {wait_secs}s for events ...");
    tokio::time::sleep(Duration::from_secs_f64(wait_secs)).await;

    println!("Received {} events", received.lock().unwrap());

    if let Some(ref uri) = sub_uri {
        let _ = events.delete_subscription(uri).await;
        println!("Subscription deleted");
    }
    listener.stop().await;
    println!("Listener stopped
Event listener sample complete");
    Ok(())
}
