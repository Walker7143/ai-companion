use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Serialize, Deserialize)]
pub struct BotConfig {
    pub bot_id: String,
    pub name: String,
    pub model: ModelConfig,
    pub memory: MemoryConfig,
    pub proactive: ProactiveConfig,
    pub platforms: Vec<PlatformConfig>,
    pub session_reset: SessionResetConfig,
}

#[derive(Serialize, Deserialize)]
pub struct ModelConfig {
    pub provider: String,
    pub api_key: String,
    pub base_url: String,
    pub model: String,
    pub temperature: f32,
    pub max_tokens: u32,
}

#[derive(Serialize, Deserialize)]
pub struct MemoryConfig {
    pub hard_limit_chars: u32,
    pub soft_limit_chars: u32,
    pub max_working_turns: u32,
    pub embedding: String,
    pub embedding_model: String,
}

#[derive(Serialize, Deserialize)]
pub struct ProactiveConfig {
    pub enabled: bool,
    pub idle_threshold_hours: u32,
    pub min_interval_hours: u32,
    pub max_daily: u32,
    pub emotion_keywords: Vec<String>,
}

#[derive(Serialize, Deserialize)]
pub struct PlatformConfig {
    pub name: String,
    pub enabled: bool,
    pub config: HashMap<String, String>,
}

#[derive(Serialize, Deserialize)]
pub struct SessionResetConfig {
    pub mode: String,
    pub at_hour: u32,
    pub idle_minutes: u32,
    pub notify: bool,
}

#[derive(Serialize)]
pub struct BotInfo {
    pub id: String,
    pub name: String,
    pub status: String,
}

#[tauri::command]
pub async fn get_config(bot_id: String) -> Result<BotConfig, String> {
    // TODO: integrate with Python AI Companion core
    Ok(BotConfig {
        bot_id: bot_id.clone(),
        name: "苏晴".to_string(),
        model: ModelConfig {
            provider: "minimax".to_string(),
            api_key: "••••••••••••".to_string(),
            base_url: "https://api.minimax.chat/v1".to_string(),
            model: "MiniMax-M2.7".to_string(),
            temperature: 0.8,
            max_tokens: 1024,
        },
        memory: MemoryConfig {
            hard_limit_chars: 5000,
            soft_limit_chars: 3000,
            max_working_turns: 20,
            embedding: "local".to_string(),
            embedding_model: "all-MiniLM-L6-v2".to_string(),
        },
        proactive: ProactiveConfig {
            enabled: true,
            idle_threshold_hours: 24,
            min_interval_hours: 3,
            max_daily: 5,
            emotion_keywords: vec![
                "难过".to_string(),
                "伤心".to_string(),
                "生气".to_string(),
                "委屈".to_string(),
                "累".to_string(),
            ],
        },
        platforms: vec![
            PlatformConfig {
                name: "cli".to_string(),
                enabled: true,
                config: HashMap::new(),
            },
            PlatformConfig {
                name: "feishu".to_string(),
                enabled: true,
                config: HashMap::from([
                    ("app_id".to_string(), "cli_xxx".to_string()),
                    ("connection_mode".to_string(), "websocket".to_string()),
                ]),
            },
        ],
        session_reset: SessionResetConfig {
            mode: "both".to_string(),
            at_hour: 4,
            idle_minutes: 1440,
            notify: true,
        },
    })
}

#[tauri::command]
pub async fn update_config(bot_id: String, config: BotConfig) -> Result<(), String> {
    // TODO: integrate with Python AI Companion core
    log::info!("Updating config for bot: {}", bot_id);
    Ok(())
}

#[tauri::command]
pub async fn get_available_bots() -> Result<Vec<BotInfo>, String> {
    // TODO: integrate with Python AI Companion core
    Ok(vec![
        BotInfo {
            id: "suqing".to_string(),
            name: "苏晴".to_string(),
            status: "running".to_string(),
        },
        BotInfo {
            id: "aiyue".to_string(),
            name: "阿月".to_string(),
            status: "running".to_string(),
        },
        BotInfo {
            id: "chenxing".to_string(),
            name: "陈行".to_string(),
            status: "stopped".to_string(),
        },
        BotInfo {
            id: "yutian".to_string(),
            name: "雨天".to_string(),
            status: "stopped".to_string(),
        },
    ])
}

#[tauri::command]
pub async fn test_api_connection(
    provider: String,
    api_key: String,
    base_url: String,
) -> Result<bool, String> {
    // TODO: implement actual connection test
    log::info!(
        "Testing API connection: provider={}, base_url={}",
        provider,
        base_url
    );
    Ok(true)
}
