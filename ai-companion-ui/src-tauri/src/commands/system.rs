use serde::Serialize;
use sysinfo::{System, CpuRefreshKind, MemoryRefreshKind, RefreshKind};

#[derive(Serialize)]
pub struct SystemMetrics {
    pub cpu_percent: f32,
    pub memory_percent: f32,
    pub memory_used_mb: u64,
    pub disk_percent: f32,
    pub uptime_seconds: u64,
}

#[derive(Serialize)]
pub struct BotMetrics {
    pub bot_id: String,
    pub status: String,
    pub uptime_seconds: u64,
    pub conversations_today: u32,
    pub proactive_messages_today: u32,
    pub input_tokens_today: u64,
    pub output_tokens_today: u64,
    pub memory_stats: MemoryStats,
}

#[derive(Serialize)]
pub struct MemoryStats {
    pub working_count: u32,
    pub working_size_kb: u64,
    pub episodic_count: u32,
    pub episodic_size_kb: u64,
    pub semantic_count: u32,
    pub semantic_size_kb: u64,
    pub embedding_enabled: bool,
}

#[tauri::command]
pub async fn get_system_metrics() -> Result<SystemMetrics, String> {
    let sys = System::new_with_specifics(
        RefreshKind::new()
            .with_cpu(CpuRefreshKind::everything())
            .with_memory(MemoryRefreshKind::everything()),
    );

    // Calculate CPU usage by averaging all CPU cores
    let cpu_percent = sys.cpus().iter().map(|cpu| cpu.cpu_usage()).sum::<f32>()
        / sys.cpus().len() as f32;

    let memory_used = sys.used_memory();
    let memory_total = sys.total_memory();
    let memory_percent = if memory_total > 0 {
        (memory_used as f32 / memory_total as f32) * 100.0
    } else {
        0.0
    };
    let memory_used_mb = memory_used / (1024 * 1024);

    let uptime_seconds = System::uptime();

    let disk_percent = 0.0; // TODO: implement disk monitoring

    Ok(SystemMetrics {
        cpu_percent,
        memory_percent,
        memory_used_mb,
        disk_percent,
        uptime_seconds,
    })
}

#[tauri::command]
pub async fn get_bot_metrics(bot_id: String) -> Result<BotMetrics, String> {
    // TODO: integrate with Python AI Companion core
    // For now, return mock data
    Ok(BotMetrics {
        bot_id,
        status: "running".to_string(),
        uptime_seconds: 86400, // 1 day
        conversations_today: 23,
        proactive_messages_today: 5,
        input_tokens_today: 12450,
        output_tokens_today: 8900,
        memory_stats: MemoryStats {
            working_count: 23,
            working_size_kb: 12,
            episodic_count: 156,
            episodic_size_kb: 89,
            semantic_count: 42,
            semantic_size_kb: 8,
            embedding_enabled: true,
        },
    })
}
