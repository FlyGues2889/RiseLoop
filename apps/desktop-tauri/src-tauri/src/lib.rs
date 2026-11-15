mod action;
mod commands;
mod notice;
mod timer;

use std::sync::atomic::{AtomicBool, Ordering};
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
const TRAY_ID: &str = "riseloop-tray";
const PAUSE_LABEL: &str = "暂停计时";
const RESUME_LABEL: &str = "继续计时";

fn pause_label(running: bool) -> &'static str {
    if running {
        PAUSE_LABEL
    } else {
        RESUME_LABEL
    }
}

fn tray_tooltip(running: bool) -> &'static str {
    if running {
        "Rise Loop · 久坐计时进行中"
    } else {
        "Rise Loop · 久坐计时已暂停"
    }
}

/// 托盘菜单是原生控件，前端改不到它：文字与提示由 Rust 侧跟着计时状态同步。
/// 只在状态真正变化时写入，避免每秒重建菜单。
fn sync_tray_menu(
    app: &tauri::AppHandle<tauri::Wry>,
    pause_item: &MenuItem<tauri::Wry>,
    running: bool,
    last_running: &AtomicBool,
) {
    if last_running.swap(running, Ordering::Relaxed) == running {
        return;
    }
    let _ = pause_item.set_text(pause_label(running));
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_tooltip(Some(tray_tooltip(running)));
    }
}

fn focus_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// 系统通知：只在自制通知窗口不可用时兜底，正常路径走 notice 窗口。
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

            // 动作会话：主窗与通知窗共用一份状态，倒计时在 Rust 侧推进，
            // 页面被隐藏时也不会被浏览器节流拖慢。
            let session = Arc::new(action::ActionSession::default());
            app.manage(session.clone());
            let action_handle = app.handle().clone();
            thread::spawn(move || loop {
                thread::sleep(Duration::from_millis(1000));
                if let Some(snapshot) = session.tick() {
                    let _ = action_handle.emit(action::ACTION_EVENT, &snapshot);
                }
            });

            // 自制通知窗口：先建好藏起来，到点直接展示，避免第一次提醒卡顿。
            app.manage(notice::NoticeState::default());
            if let Err(error) = notice::create_window(app.handle()) {
                eprintln!("notice window unavailable, fallback to system toast: {error}");
            }

            // 调试用：RISELOOP_NOTICE_DEMO=1 启动，3 秒后弹一条样例通知，
            // 不必真的坐满 45 分钟也能验收通知窗口。
            #[cfg(debug_assertions)]
            if std::env::var_os("RISELOOP_NOTICE_DEMO").is_some() {
                let demo = app.handle().clone();
                thread::spawn(move || {
                    thread::sleep(Duration::from_secs(3));
                    notice::show(
                        &demo,
                        notice::NoticePayload {
                            title: "该起身了".to_string(),
                            body: "已经连续久坐 46 分钟。".to_string(),
                            sitting_minutes: 46,
                            action: Some(notice::NoticeAction {
                                name: "起身站立微活动".to_string(),
                                duration_minutes: 3,
                                steps: vec![
                                    "起身离开座位".to_string(),
                                    "原地抬膝 10 次".to_string(),
                                    "颈肩绕环 30 秒".to_string(),
                                ],
                                source: Some("动作依据 · 主动休息".to_string()),
                            }),
                        },
                    );
                    // 再等 6 秒自动展开，验收“原地变形”的动画与布局
                    thread::sleep(Duration::from_secs(6));
                    let _ = demo.emit_to("notice", "riseloop://notice-expand", ());
                });
            }

            // 点击系统通知（tap）时把主窗口唤回前台；插件只在通知仍在屏幕时上报点击。
            let notification_handle = app.handle().clone();
            app.notification().on_action(move |_action| {
                let handle = notification_handle.clone();
                let focus_handle = handle.clone();
                let _ = handle.run_on_main_thread(move || focus_main_window(&focus_handle));
            })?;

            let open_item = MenuItem::with_id(app, "open", "打开 Rise Loop", true, None::<&str>)?;
            let initial_running = timer.snapshot().running;
            let pause_item = MenuItem::with_id(
                app,
                "pause",
                pause_label(initial_running),
                true,
                None::<&str>,
            )?;
            let reset_item = MenuItem::with_id(app, "reset", "重新计时", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &pause_item, &reset_item, &quit_item])?;

            let pause_running = Arc::new(AtomicBool::new(initial_running));
            let menu_pause_item = pause_item.clone();
            let menu_running = pause_running.clone();

            let tray_timer = timer.clone();
            TrayIconBuilder::with_id(TRAY_ID)
                .icon(
                    app.default_window_icon()
                        .cloned()
                        .expect("missing app icon"),
                )
                .tooltip(tray_tooltip(initial_running))
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "open" => focus_main_window(app),
                    // 同一项切换：运行中就暂停，已暂停就继续
                    "pause" => {
                        let snapshot = tray_timer.toggle();
                        sync_tray_menu(app, &menu_pause_item, snapshot.running, &menu_running);
                        let _ = app.emit(TICK_EVENT, &snapshot);
                    }
                    // 重置后立刻开新一轮，不停在“已清零但没开始”
                    "reset" => {
                        let snapshot = tray_timer.restart();
                        sync_tray_menu(app, &menu_pause_item, snapshot.running, &menu_running);
                        let _ = app.emit(TICK_EVENT, &snapshot);
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
            let tick_pause_item = pause_item.clone();
            let tick_running = pause_running.clone();
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(1));
                let snapshot = tick_timer.snapshot();
                // 前端按钮、心跳自动暂停也会改状态，这里兜住托盘文字
                sync_tray_menu(&handle, &tick_pause_item, snapshot.running, &tick_running);
                let _ = handle.emit(TICK_EVENT, &snapshot);
                if let Some(triggered) = tick_timer.tick() {
                    // 自制通知优先；窗口没建起来时回退系统通知
                    let minutes = triggered.sitting_seconds / 60;
                    let shown = notice::show(
                        &handle,
                        notice::NoticePayload {
                            title: "该起身了".to_string(),
                            body: format!("已经连续久坐 {minutes} 分钟。"),
                            sitting_minutes: minutes,
                            action: None,
                        },
                    );
                    if !shown {
                        notify_break(&handle, &triggered);
                    }
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
            commands::timer_restart,
            commands::timer_seed_elapsed,
            commands::timer_set_threshold,
            commands::store_session_token,
            commands::load_session_token,
            commands::clear_session_token,
            commands::camera_log,
            commands::camera_log_path,
            notice::notice_current,
            notice::notice_resize,
            notice::notice_dismiss,
            notice::notice_set_action,
            notice::notice_start,
            notice::notice_open_main,
            action::action_state,
            action::action_load,
            action::action_play,
            action::action_pause,
            action::action_toggle,
            action::action_next,
            action::action_prev,
            action::action_restart,
            action::action_finish,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
