use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Serialize, Deserialize)]
pub struct SessionInfo {
    pub session_key: String,
    pub session_id: String,
    pub platform: String,
    pub user: String,
    pub created_at: String,
    pub updated_at: String,
    pub status: String,
    pub reset_reason: Option<String>,
    pub total_tokens: u64,
}

#[derive(Serialize)]
pub struct SessionDetail {
    pub info: SessionInfo,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_write_tokens: u64,
    pub cache_read_tokens: u64,
    pub estimated_cost_usd: f64,
}

#[derive(Serialize)]
pub struct ContextDetail {
    pub system_prompt: String,
    pub working_history: Vec<Message>,
    pub episodic_recall: Vec<EpisodicItem>,
    pub semantic_facts: HashMap<String, String>,
    pub system_suffix: String,
    pub compression_history: Vec<CompressionRecord>,
    pub current_tokens: u32,
    pub hard_limit: u32,
    pub soft_limit: u32,
}

#[derive(Serialize)]
pub struct Message {
    pub id: String,
    pub role: String,
    pub content: String,
    pub created_at: String,
}

#[derive(Serialize)]
pub struct EpisodicItem {
    pub id: String,
    pub summary: String,
    pub content: String,
    pub importance: f32,
    pub created_at: String,
    pub related_session: String,
}

#[derive(Serialize)]
pub struct CompressionRecord {
    pub timestamp: String,
    pub original_chars: u32,
    pub compressed_chars: u32,
    pub savings_percent: f32,
}

#[tauri::command]
pub async fn list_sessions(bot_id: String) -> Result<Vec<SessionInfo>, String> {
    // TODO: integrate with Python AI Companion core
    Ok(vec![SessionInfo {
        session_key: "20260426_143215_a1b2c3d4".to_string(),
        session_id: "20260426_143215".to_string(),
        platform: "cli".to_string(),
        user: "localhost".to_string(),
        created_at: "2026-04-26T14:32:15".to_string(),
        updated_at: "2026-04-26T16:30:00".to_string(),
        status: "active".to_string(),
        reset_reason: None,
        total_tokens: 4380,
    }])
}

#[tauri::command]
pub async fn get_session_detail(session_key: String) -> Result<SessionDetail, String> {
    // TODO: integrate with Python AI Companion core
    Ok(SessionDetail {
        info: SessionInfo {
            session_key: session_key.clone(),
            session_id: "20260426_143215".to_string(),
            platform: "cli".to_string(),
            user: "localhost".to_string(),
            created_at: "2026-04-26T14:32:15".to_string(),
            updated_at: "2026-04-26T16:30:00".to_string(),
            status: "active".to_string(),
            reset_reason: None,
            total_tokens: 4380,
        },
        input_tokens: 1234,
        output_tokens: 2456,
        cache_write_tokens: 567,
        cache_read_tokens: 123,
        estimated_cost_usd: 0.0123,
    })
}

#[tauri::command]
pub async fn reset_session(session_key: String) -> Result<(), String> {
    // TODO: integrate with Python AI Companion core
    log::info!("Resetting session: {}", session_key);
    Ok(())
}

#[tauri::command]
pub async fn suspend_session(session_key: String) -> Result<(), String> {
    // TODO: integrate with Python AI Companion core
    log::info!("Suspending session: {}", session_key);
    Ok(())
}

#[tauri::command]
pub async fn get_session_context(session_key: String) -> Result<ContextDetail, String> {
    // TODO: integrate with Python AI Companion core
    let mut semantic_facts = HashMap::new();
    semantic_facts.insert("职业".to_string(), "程序员".to_string());
    semantic_facts.insert("城市".to_string(), "上海".to_string());
    semantic_facts.insert("关系状态".to_string(), "暧昧期".to_string());
    semantic_facts.insert("好感度".to_string(), "+6".to_string());

    Ok(ContextDetail {
        system_prompt: "你叫苏晴，26岁自由插画师，性格傲娇...".to_string(),
        working_history: vec![
            Message {
                id: "1".to_string(),
                role: "user".to_string(),
                content: "今天加班好累".to_string(),
                created_at: "2026-04-26T14:32:15".to_string(),
            },
            Message {
                id: "2".to_string(),
                role: "assistant".to_string(),
                content: "又加班了吗...要注意身体啊笨蛋".to_string(),
                created_at: "2026-04-26T14:32:16".to_string(),
            },
        ],
        episodic_recall: vec![
            EpisodicItem {
                id: "e1".to_string(),
                summary: "上次加班到很晚，她说笨蛋...".to_string(),
                content: "用户上次加班到很晚，Bot发了关心消息".to_string(),
                importance: 4.5,
                created_at: "2026-04-24T22:00:00".to_string(),
                related_session: "20260424_xxx".to_string(),
            },
        ],
        semantic_facts,
        system_suffix: "当前话题: 工作压力大\n情绪状态: 用户比较疲惫，需要关心但不要太啰嗦".to_string(),
        compression_history: vec![
            CompressionRecord {
                timestamp: "2026-04-26T14:20:00".to_string(),
                original_chars: 3200,
                compressed_chars: 890,
                savings_percent: 72.0,
            },
        ],
        current_tokens: 2450,
        hard_limit: 5000,
        soft_limit: 3000,
    })
}
