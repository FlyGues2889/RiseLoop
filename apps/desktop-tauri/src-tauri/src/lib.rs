mod commands;
mod timer;

use std::sync::Arc;
use std::thread;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, WindowEvent};
use tauri_plugin_notification::NotificationExt;

use timer::{SittingTimer, TimerSnapshot, DEFAULT_THRESHOLD_MINUTES};

const THRESHOLD_EVENT: &str = "riseloop://threshold";
const TICK_EVENT: &str = "riseloop://tick";

fn focus_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn notify_break(app: &tauri::AppHandle, snapshot: &TimerSnapshot) {
    let minutes = snapshot.sitting_seconds / 60;
    let _ = app
        .notification()
        .builder()
        .title("该起身了")
        .body(format!(
            "已连续久坐 {minutes} 分钟，做一个 2 分钟的最短有效动作。"
        ))
        .show();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let timer = Arc::new(SittingTimer::new(DEFAULT_THRESHOLD_MINUTES));
            app.manage(timer.clone());

            // 点击系统通知（tap）时把主窗口唤回前台；插件只在通知仍在屏幕时上报点击。
            let notification_handle = app.handle().clone();
            app.notification().on_action(move |_action| {
                let handle = notification_handle.clone();
                let focus_handle = handle.clone();
                let _ = handle.run_on_main_thread(move || focus_main_window(&focus_handle));
            })?;

            let open_item = MenuItem::with_id(app, "open", "打开 Rise Loop", true, None::<&str>)?;
            let pause_item = MenuItem::with_id(app, "pause", "暂停计时", true, None::<&str>)?;
            let reset_item = MenuItem::with_id(app, "reset", "重新计时", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &pause_item, &reset_item, &quit_item])?;

            let tray_timer = timer.clone();
            TrayIconBuilder::with_id("riseloop-tray")
                .icon(
                    app.default_window_icon()
                        .cloned()
                        .expect("missing app icon"),
                )
                .tooltip("Rise Loop 久坐提醒")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "open" => focus_main_window(app),
                    "pause" => {
                        tray_timer.pause();
                    }
                    "reset" => {
                        tray_timer.reset();
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        focus_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            let handle = app.handle().clone();
            let tick_timer = timer.clone();
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(1));
                let snapshot = tick_timer.snapshot();
                let _ = handle.emit(TICK_EVENT, &snapshot);
                if let Some(triggered) = tick_timer.tick() {
                    notify_break(&handle, &triggered);
                    let _ = handle.emit(THRESHOLD_EVENT, &triggered);
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::timer_state,
            commands::timer_start,
            commands::timer_pause,
            commands::timer_reset,
            commands::timer_seed_elapsed,
            commands::timer_set_threshold,
            commands::store_session_token,
            commands::load_session_token,
            commands::clear_session_token,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
