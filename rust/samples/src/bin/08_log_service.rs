use futures::StreamExt;
use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, LogQuery, RedfishError};

fn parse_args() -> (String, u16, String, String, bool, usize) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut max_entries = 5usize;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            "--max-entries"   => { max_entries = it.next().unwrap().parse().unwrap(); }
            _ => {}
        }
    }
    (host, port, user, password, no_tls, max_entries)
}

#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls, max_entries) = parse_args();
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() }).await?;
    let logs = ctx.log_service();

    println!("Listing log services ...");
    let svc_resp = logs.list_services().await?;
    if !svc_resp.success { eprintln!("  HTTP {}", svc_resp.status_code); return Ok(()); }

    let services: Vec<String> = svc_resp.body.as_ref()
        .and_then(|b| b["Members"].as_array())
        .map(|a| a.iter().filter_map(|v| v["@odata.id"].as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    println!("  Found {} log service(s)", services.len());

    for svc_uri in &services {
        let q = LogQuery { top: Some(max_entries), ..Default::default() };
        let er = logs.list_entries(svc_uri, q).await?;
        if !er.success { println!("    HTTP {}", er.status_code); continue; }

        let entries = er.body.as_ref().and_then(|b| b["Members"].as_array()).cloned().unwrap_or_default();
        let total = er.body.as_ref().and_then(|b| b["Members@odata.count"].as_u64()).unwrap_or(entries.len() as u64);
        println!("    Total: {total}  (showing {})", entries.len().min(max_entries));

        for e in entries.iter().take(max_entries) {
            let id  = e["Id"].as_str().unwrap_or("?");
            let sev = e["Severity"].as_str().or_else(|| e["MessageSeverity"].as_str()).unwrap_or("?");
            let msg = e["Message"].as_str().unwrap_or("").chars().take(60).collect::<String>();
            println!("    [{id:>6}] {sev:<12} {msg}");
        }

        // iter_entries stream
        println!("    Streaming (limit 5) ...");
        let sq = LogQuery { top: Some(5), ..Default::default() };
        let mut stream = logs.iter_entries(svc_uri, sq, Some(1));
        let mut n = 0usize;
        while let Some(r) = stream.next().await {
            match r {
                Ok(page) => {
                    if let Some(b) = &page.body {
                        if let Some(arr) = b["Members"].as_array() {
                            for e in arr { n += 1; println!("      [stream {n}] id={}", e["Id"].as_str().unwrap_or("?")); }
                        }
                    }
                    if n >= 5 { break; }
                }
                Err(e) => { eprintln!("      stream error: {e}"); break; }
            }
        }
    }

    if let Some(first_uri) = services.first() {
        println!("\nAttempting to clear log: {first_uri}");
        let cr = logs.clear_log(first_uri).await?;
        if cr.success { println!("  Log cleared"); }
        else { println!("  HTTP {} (may not be supported)", cr.status_code); }
    }

    println!("\nLog service sample complete");
    Ok(())
}
