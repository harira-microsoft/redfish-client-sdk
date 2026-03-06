use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError};

fn parse_args() -> (String, u16, String, String, bool, String, bool) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut image_uri = "http://fileserver.example.com/firmware.bin".to_string();
    let mut dry_run = false;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            "--image-uri"     => { image_uri = it.next().unwrap(); }
            "--dry-run"       => { dry_run = true; }
            _ => {}
        }
    }
    (host, port, user, password, no_tls, image_uri, dry_run)
}

#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls, image_uri, dry_run) = parse_args();
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() }).await?;
    let update = ctx.update_service();

    println!("Firmware inventory:");
    let fwr = update.list_firmware_inventory().await?;
    let mut target_uri: Option<String> = None;
    if fwr.success {
        let members = fwr.body.as_ref().and_then(|b| b["Members"].as_array()).cloned().unwrap_or_default();
        println!("  Items: {}", members.len());
        for item in &members {
            let iu = item["@odata.id"].as_str().unwrap_or("");
            let d = ctx.get(iu).await?;
            if d.success {
                if let Some(b) = &d.body {
                    println!("    {:<20} {:<30} v{}", b["Id"].as_str().unwrap_or("?"), b["Name"].as_str().unwrap_or(""), b["Version"].as_str().unwrap_or("?"));
                }
            }
        }
        if !members.is_empty() { target_uri = members[0]["@odata.id"].as_str().map(str::to_string); }
    }

    println!("\nSoftware inventory:");
    let swr = update.list_software_inventory().await?;
    if swr.success {
        let members = swr.body.as_ref().and_then(|b| b["Members"].as_array()).cloned().unwrap_or_default();
        println!("  Items: {}", members.len());
    }

    if dry_run {
        println!("\n[DRY RUN] Skipping SimpleUpdate");
    } else {
        let targets: Vec<String> = target_uri.into_iter().collect();
        println!("\nCalling SimpleUpdate: {image_uri}");
        let ur = update.simple_update(&image_uri, targets, Some("HTTP"), Some("Immediate")).await?;
        if let Some(task) = ur.task {
            println!("  Task created: {}", task.task_uri);
            // Manual poll loop (avoids Fn/move borrow constraints on task.wait)
            let mut state = task.state.clone();
            for _ in 0..15 {
                tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                let pr = ctx.get(&task.task_uri).await?;
                if let Some(b) = &pr.body {
                    if let Some(s) = b["TaskState"].as_str() { state = s.to_string(); }
                }
                println!("  Task state: {state}");
                match state.as_str() {
                    "Completed" | "Killed" | "Exception" | "Cancelled" => break,
                    _ => {}
                }
            }
            println!("  Final task state: {state}");
        } else if ur.success {
            println!("  Update completed synchronously ({})", ur.status_code);
        } else {
            println!("  HTTP {}", ur.status_code);
        }
    }

    println!("\nUpdate service sample complete");
    Ok(())
}
