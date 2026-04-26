pub mod commands;

use log::info;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("Starting AI Companion Admin Dashboard...");

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            commands::system::get_system_metrics,
            commands::system::get_bot_metrics,
            commands::session::list_sessions,
            commands::session::get_session_detail,
            commands::session::reset_session,
            commands::session::suspend_session,
            commands::session::get_session_context,
            commands::memory::get_memory_stats,
            commands::memory::get_working_memory,
            commands::memory::get_episodic_memory,
            commands::memory::get_semantic_memory,
            commands::memory::delete_memory,
            commands::memory::clear_all_memory,
            commands::logs::get_logs,
            commands::config::get_config,
            commands::config::update_config,
            commands::config::get_available_bots,
            commands::config::test_api_connection,
            commands::process::start_bot,
            commands::process::stop_bot,
            commands::process::restart_bot,
            commands::process::get_bot_status,
            commands::process::list_processes,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
