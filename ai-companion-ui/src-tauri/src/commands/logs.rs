use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

#[derive(Clone, Serialize)]
pub struct LogStreamEvent {
    pub id: String,
    pub timestamp: String,
    pub level: String,
    pub log_type: String,
    pub platform: String,
    pub message: String,
}

pub struct LogStreamState {
    pub logs: VecDeque<LogEntry>,
    pub is_streaming: bool,
}

impl Default for LogStreamState {
    fn default() -> Self {
        Self {
            logs: VecDeque::new(),
            is_streaming: false,
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct LogParams {
    pub bot_id: String,
    pub level: Option<String>,
    pub log_type: Option<String>,
    pub date: Option<String>,
    pub query: Option<String>,
    pub page: u32,
    pub page_size: u32,
}

#[derive(Serialize)]
pub struct LogPage {
    pub logs: Vec<LogEntry>,
    pub total: u32,
    pub page: u32,
    pub page_size: u32,
    pub total_pages: u32,
}

#[derive(Serialize)]
pub struct LogEntry {
    pub id: String,
    pub timestamp: String,
    pub level: String,
    pub log_type: String,
    pub platform: String,
    pub message: String,
    pub details: Option<String>,
}

#[tauri::command]
pub async fn get_logs(params: LogParams) -> Result<LogPage, String> {
    // TODO: integrate with Python AI Companion core
    // For now, return mock data
    let logs = vec![
        LogEntry {
            id: "1".to_string(),
            timestamp: "2026-04-26T14:32:15.234".to_string(),
            level: "info".to_string(),
            log_type: "dialogue".to_string(),
            platform: "cli".to_string(),
            message: "user → bot: 「今天工作好累啊」".to_string(),
            details: None,
        },
        LogEntry {
            id: "2".to_string(),
            timestamp: "2026-04-26T14:32:15.456".to_string(),
            level: "info".to_string(),
            log_type: "session".to_string(),
            platform: "cli".to_string(),
            message: "加载上下文: working=4, episodic=3, semantic=42".to_string(),
            details: None,
        },
        LogEntry {
            id: "3".to_string(),
            timestamp: "2026-04-26T14:32:16.100".to_string(),
            level: "info".to_string(),
            log_type: "api".to_string(),
            platform: "cli".to_string(),
            message: "MiniMax.chat: tokens=1234/2345, 延迟=215ms".to_string(),
            details: Some(r#"{"input_tokens": 1234, "output_tokens": 456, "latency_ms": 215}"#.to_string()),
        },
        LogEntry {
            id: "4".to_string(),
            timestamp: "2026-04-26T14:32:17.123".to_string(),
            level: "info".to_string(),
            log_type: "dialogue".to_string(),
            platform: "cli".to_string(),
            message: "bot → user: 「又加班了吗...要注意身体啊笨蛋」".to_string(),
            details: None,
        },
        LogEntry {
            id: "5".to_string(),
            timestamp: "2026-04-26T14:31:45.000".to_string(),
            level: "info".to_string(),
            log_type: "proactive".to_string(),
            platform: "feishu".to_string(),
            message: "检测空闲触发: 24h30m > 阈值24h".to_string(),
            details: None,
        },
    ];

    let total = 5;
    let total_pages = (total + params.page_size - 1) / params.page_size;

    Ok(LogPage {
        logs,
        total,
        page: params.page,
        page_size: params.page_size,
        total_pages,
    })
}

#[tauri::command]
pub async fn stream_logs(
    bot_id: String,
    app: AppHandle,
    state: tauri::State<'_, Arc<Mutex<LogStreamState>>>,
) -> Result<(), String> {
    log::info!("Starting log stream for bot: {}", bot_id);

    {
        let mut state = state.lock().map_err(|e| e.to_string())?;
        state.is_streaming = true;
    }

    // Simulate streaming log events
    let logs = vec![
        LogStreamEvent {
            id: "s1".to_string(),
            timestamp: "2026-04-26T14:32:15.234".to_string(),
            level: "info".to_string(),
            log_type: "dialogue".to_string(),
            platform: "cli".to_string(),
            message: "user → bot: 「今天工作好累啊」".to_string(),
        },
        LogStreamEvent {
            id: "s2".to_string(),
            timestamp: "2026-04-26T14:32:15.456".to_string(),
            level: "info".to_string(),
            log_type: "session".to_string(),
            platform: "cli".to_string(),
            message: "加载上下文: working=4, episodic=3, semantic=42".to_string(),
        },
        LogStreamEvent {
            id: "s3".to_string(),
            timestamp: "2026-04-26T14:32:16.100".to_string(),
            level: "info".to_string(),
            log_type: "api".to_string(),
            platform: "cli".to_string(),
            message: "MiniMax.chat: tokens=1234/2345, 延迟=215ms".to_string(),
        },
    ];

    for log_entry in logs {
        app.emit("log-event", &log_entry)
            .map_err(|e| e.to_string())?;
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }

    {
        let mut state = state.lock().map_err(|e| e.to_string())?;
        state.is_streaming = false;
    }

    Ok(())
}

#[tauri::command]
pub async fn export_logs(
    bot_id: String,
    format: String,
    path: String,
) -> Result<String, String> {
    log::info!(
        "Exporting logs for bot: {}, format: {}, path: {}",
        bot_id,
        format,
        path
    );

    // TODO: integrate with Python AI Companion core to get actual logs
    // For now, return a mock export result

    let content = match format.as_str() {
        "json" => serde_json::to_string_pretty(&vec![
            LogEntry {
                id: "1".to_string(),
                timestamp: "2026-04-26T14:32:15.234".to_string(),
                level: "info".to_string(),
                log_type: "dialogue".to_string(),
                platform: "cli".to_string(),
                message: "user → bot: 「今天工作好累啊」".to_string(),
                details: None,
            },
            LogEntry {
                id: "2".to_string(),
                timestamp: "2026-04-26T14:32:16.100".to_string(),
                level: "info".to_string(),
                log_type: "api".to_string(),
                platform: "cli".to_string(),
                message: "MiniMax.chat: tokens=1234/2345, 延迟=215ms".to_string(),
                details: Some(r#"{"input_tokens": 1234, "output_tokens": 456, "latency_ms": 215}"#.to_string()),
            },
        ])
        .map_err(|e| e.to_string())?,
        "csv" => "id,timestamp,level,log_type,platform,message\n\
                  1,2026-04-26T14:32:15.234,info,dialogue,cli,\"user → bot: 今天工作好累啊\"\n\
                  2,2026-04-26T14:32:16.100,info,api,cli,\"MiniMax.chat: tokens=1234/2345, 延迟=215ms\""
            .to_string(),
        _ => return Err(format!("Unsupported export format: {}", format)),
    };

    // For security reasons, we don't actually write files in the Tauri command
    // The frontend should handle the file writing or use Tauri's fs API
    // Here we just return the content for the frontend to handle
    Ok(content)
}
