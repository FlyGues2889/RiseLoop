use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;

use tauri::Manager;
use tauri::State;

use crate::timer::{SittingTimer, TimerSnapshot};

const KEYRING_SERVICE: &str = "com.riseloop.app";
const KEYRING_ACCOUNT: &str = "session-token";
/// 访问令牌一小时过期，刷新令牌单独一格，续期时只换访问令牌
const KEYRING_ACCOUNT_REFRESH: &str = "refresh-token";

#[tauri::command]
pub fn timer_state(timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.snapshot()
}

#[tauri::command]
pub fn timer_start(timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.start()
}

#[tauri::command]
pub fn timer_pause(timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.pause()
}

#[tauri::command]
pub fn timer_reset(timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.reset()
}

#[tauri::command]
pub fn timer_restart(timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.restart()
}

#[tauri::command]
pub fn timer_seed_elapsed(minutes: u64, timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.seed_elapsed(minutes)
}

#[tauri::command]
pub fn timer_set_threshold(minutes: u64, timer: State<'_, Arc<SittingTimer>>) -> Result<TimerSnapshot, String> {
    timer.set_threshold(minutes)
}

fn keyring_entry(account: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, account).map_err(|error| error.to_string())
}

fn store_secret(account: &str, secret: &str) -> Result<(), String> {
    keyring_entry(account)?.set_password(secret).map_err(|error| error.to_string())
}

fn load_secret(account: &str) -> Result<Option<String>, String> {
    match keyring_entry(account)?.get_password() {
        Ok(secret) => Ok(Some(secret)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(error.to_string()),
    }
}

fn clear_secret(account: &str) -> Result<(), String> {
    match keyring_entry(account)?.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
pub fn store_session_token(token: String) -> Result<(), String> {
    store_secret(KEYRING_ACCOUNT, &token)
}

#[tauri::command]
pub fn load_session_token() -> Result<Option<String>, String> {
    load_secret(KEYRING_ACCOUNT)
}

#[tauri::command]
pub fn clear_session_token() -> Result<(), String> {
    clear_secret(KEYRING_ACCOUNT)
}

#[tauri::command]
pub fn store_refresh_token(token: String) -> Result<(), String> {
    store_secret(KEYRING_ACCOUNT_REFRESH, &token)
}

#[tauri::command]
pub fn load_refresh_token() -> Result<Option<String>, String> {
    load_secret(KEYRING_ACCOUNT_REFRESH)
}

#[tauri::command]
pub fn clear_refresh_token() -> Result<(), String> {
    clear_secret(KEYRING_ACCOUNT_REFRESH)
}

fn camera_log_path_of(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_log_dir().map_err(|error| error.to_string())?;
    Ok(dir.join("camera.log"))
}

fn append_camera_log(path: &std::path::Path, line: &str) -> Result<(), String> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|error| error.to_string())?;
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    writeln!(file, "{line}").map_err(|error| error.to_string())
}

/// 追加一行摄像头记录：时间、类型、说明由前端拼好，这里只负责落盘。
#[tauri::command]
pub fn camera_log(app: tauri::AppHandle, line: String) -> Result<(), String> {
    let path = camera_log_path_of(&app)?;
    append_camera_log(&path, &line)
}

#[tauri::command]
pub fn camera_log_path(app: tauri::AppHandle) -> Result<String, String> {
    Ok(camera_log_path_of(&app)?.display().to_string())
}

fn capture_path_of(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|error| error.to_string())?;
    Ok(dir.join("capture").join("frames.jsonl"))
}

fn append_lines(path: &std::path::Path, lines: &[String]) -> Result<(), String> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|error| error.to_string())?;
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    for line in lines {
        writeln!(file, "{line}").map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// 追加若干行已序列化好的关键点记录，返回落盘路径。
#[tauri::command]
pub fn capture_append(app: tauri::AppHandle, lines: Vec<String>) -> Result<String, String> {
    let path = capture_path_of(&app)?;
    append_lines(&path, &lines)?;
    Ok(path.display().to_string())
}

#[tauri::command]
pub fn capture_path(app: tauri::AppHandle) -> Result<String, String> {
    Ok(capture_path_of(&app)?.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::{append_camera_log, append_lines};

    #[test]
    fn camera_log_appends_instead_of_truncating() {
        let dir = std::env::temp_dir().join(format!("riseloop-camera-log-{}", std::process::id()));
        let path = dir.join("nested").join("camera.log");
        let _ = std::fs::remove_dir_all(&dir);
        append_camera_log(&path, "open\t打开摄像头采样").unwrap();
        append_camera_log(&path, "close\t摄像头已关闭").unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        assert_eq!(text.lines().count(), 2);
        assert!(text.contains("打开摄像头采样"));
        assert!(text.contains("摄像头已关闭"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn capture_append_creates_directory_and_keeps_lines() {
        let dir = std::env::temp_dir().join(format!("riseloop-capture-{}", std::process::id()));
        let path = dir.join("capture").join("frames.jsonl");
        let _ = std::fs::remove_dir_all(&dir);

        append_lines(&path, &["{\"a\":1}".to_string()]).unwrap();
        append_lines(&path, &["{\"a\":2}".to_string(), "{\"a\":3}".to_string()]).unwrap();

        let text = std::fs::read_to_string(&path).unwrap();
        assert_eq!(text.lines().count(), 3);
        assert!(text.starts_with("{\"a\":1}"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
