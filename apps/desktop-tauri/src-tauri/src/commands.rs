use std::sync::Arc;

use tauri::State;

use crate::timer::{SittingTimer, TimerSnapshot};

const KEYRING_SERVICE: &str = "com.sitloop.app";
const KEYRING_ACCOUNT: &str = "session-token";

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
pub fn timer_seed_elapsed(minutes: u64, timer: State<'_, Arc<SittingTimer>>) -> TimerSnapshot {
    timer.seed_elapsed(minutes)
}

#[tauri::command]
pub fn timer_set_threshold(minutes: u64, timer: State<'_, Arc<SittingTimer>>) -> Result<TimerSnapshot, String> {
    timer.set_threshold(minutes)
}

#[tauri::command]
pub fn store_session_token(token: String) -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|error| error.to_string())?;
    entry.set_password(&token).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn load_session_token() -> Result<Option<String>, String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|error| error.to_string())?;
    match entry.get_password() {
        Ok(token) => Ok(Some(token)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
pub fn clear_session_token() -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|error| error.to_string())?;
    match entry.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}