use std::{sync::{atomic::{AtomicU64, Ordering}, Arc}, time::Duration};
use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError, RedfishEventListener};

fn parse_args() -> (String, u16, String, String, bool, u16, f64) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut listen_port = 9091u16;
    let mut wait = 15.0f64;
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
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() }).await?;

    let mut listener = RedfishEventListener::new(listen_port);

    let total = Arc::new(AtomicU64::new(0));
    let alerts = Arc::new(AtomicU64::new(0));
    let status_c = Arc::new(AtomicU64::new(0));
    let base_r = Arc::new(AtomicU64::new(0));

    let tc = Arc::clone(&total);
    listener.on_event(move |ev| {
        tc.fetch_add(1, Ordering::Relaxed);
        println!("  [ALL      ] {} - {}", ev.event_type, ev.message_id);
    });
    let ac = Arc::clone(&alerts);
    listener.on_event_type("Alert", move |ev| {
        ac.fetch_add(1, Ordering::Relaxed);
        println!("  [ALERT   ] sev={:?}", ev.severity);
    });
    let sc = Arc::clone(&status_c);
    listener.on_event_type("StatusChange", move |_ev| {
        sc.fetch_add(1, Ordering::Relaxed);
        println!("  [STATUS  ] StatusChange received");
    });
    let bc = Arc::clone(&base_r);
    listener.on_registry("Base", move |ev| {
        bc.fetch_add(1, Ordering::Relaxed);
        println!("  [BASE.REG] {} - {}", ev.message_id, ev.message);
    });

    listener.start().await?;
    println!("Listener active on 0.0.0.0:{listen_port}");

    let dest = format!("http://127.0.0.1:{listen_port}");
    let events = ctx.event_service();
    let sr = events.subscribe(
        &dest,
        vec!["Alert".into(), "ResourceUpdated".into(), "StatusChange".into()],
        vec![], vec![], vec![], None, Some("RSDK-Sample-07"), "Redfish", "RedfishEvent",
    ).await?;

    let sub_uri: Option<String> = if sr.success {
        let uri = sr.body.as_ref().and_then(|b| b["@odata.id"].as_str()).map(str::to_string);
        println!("Subscribed - {}", uri.as_deref().unwrap_or("?"));
        uri
    } else {
        println!("Subscribe HTTP {}", sr.status_code);
        None
    };

    for _ in 0..3 {
        let _ = events.submit_test_event(serde_json::json!({})).await;
        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    println!("Waiting {wait_secs}s ...");
    tokio::time::sleep(Duration::from_secs_f64(wait_secs)).await;

    println!("
-- Event statistics --");
    println!("  total         : {}", total.load(Ordering::Relaxed));
    println!("  alerts        : {}", alerts.load(Ordering::Relaxed));
    println!("  status_change : {}", status_c.load(Ordering::Relaxed));
    println!("  base_registry : {}", base_r.load(Ordering::Relaxed));

    let ip_stats = listener.get_ip_stats().await;
    println!("
-- Per-IP counts --");
    for (ip, count) in &ip_stats { println!("  {ip}: {count}"); }

    if let Some(ref uri) = sub_uri { let _ = events.delete_subscription(uri).await; }
    listener.stop().await;
    println!("
Event monitor sample complete");
    Ok(())
}
