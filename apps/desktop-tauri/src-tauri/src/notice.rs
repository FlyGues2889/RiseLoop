//! 自制通知窗口：右下角悬浮卡片，点击后原地展开为方案小窗。
//!
//! 系统通知（tauri-plugin-notification）保留为兜底：窗口创建失败或平台不支持透明窗口时回退。

use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, State, WebviewUrl,
    WebviewWindow, WebviewWindowBuilder, Wry,
};

pub const NOTICE_LABEL: &str = "notice";
/// 新通知到达时推给通知窗口
pub const NOTICE_EVENT: &str = "riseloop://notice";
/// 主窗口算好动作后补推给通知窗口
pub const NOTICE_ACTION_EVENT: &str = "riseloop://notice-action";
/// 用户在通知里点「开始」，主窗口接住去展示干预
pub const NOTICE_START_EVENT: &str = "riseloop://notice-start";

const WIDTH: f64 = 380.0;
const COLLAPSED_HEIGHT: f64 = 168.0;
const MIN_HEIGHT: f64 = 120.0;
const MAX_HEIGHT: f64 = 640.0;
/// 距屏幕工作区右下角的留白
const MARGIN: f64 = 16.0;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoticeAction {
    pub name: String,
    pub duration_minutes: u64,
    pub steps: Vec<String>,
    pub source: Option<String>,
    /// 安全警示，主窗与通知窗共用同一份文案
    #[serde(default)]
    pub caution: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoticePayload {
    pub title: String,
    pub body: String,
    pub sitting_minutes: u64,
    #[serde(default)]
    pub action: Option<NoticeAction>,
}

/// 通知窗口当前展示的内容。主窗口是业务真相，这里只做展示缓存。
#[derive(Default)]
pub struct NoticeState {
    payload: Mutex<Option<NoticePayload>>,
    /// 上次应用过的窗口高度，用来跳过无变化的重复 resize
    last_height: Mutex<f64>,
    /// 上次设置的 focusable 状态。反复切换窗口样式会让窗口重绘闪烁，没变化就不碰
    focusable: Mutex<Option<bool>>,
}

pub fn create_window(app: &AppHandle<Wry>) -> tauri::Result<WebviewWindow<Wry>> {
    let window = WebviewWindowBuilder::new(app, NOTICE_LABEL, WebviewUrl::App("notice.html".into()))
        .title("Rise Loop 提醒")
        .inner_size(WIDTH, COLLAPSED_HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(false)
        .build()?;
    // 折叠态不抢焦点：用户正在别的窗口打字时也不打断
    let _ = window.set_focusable(false);
    Ok(window)
}

/// 弹出一条通知；窗口不可用时返回 false，调用方回退到系统通知。
pub fn show(app: &AppHandle<Wry>, payload: NoticePayload) -> bool {
    if let Some(state) = app.try_state::<NoticeState>() {
        if let Ok(mut current) = state.payload.lock() {
            *current = Some(payload);
        }
    }
    reveal(app)
}

/// 按当前缓存的内容把窗口展示出来（内容已存在时复用，不重置业务数据）。
fn reveal(app: &AppHandle<Wry>) -> bool {
    let Some(window) = app.get_webview_window(NOTICE_LABEL) else {
        return false;
    };
    let Some(payload) = app
        .try_state::<NoticeState>()
        .and_then(|state| state.payload.lock().ok().and_then(|current| current.clone()))
    else {
        return false;
    };
    set_focusable(app, &window, false);
    if let Err(error) = place(app, &window, COLLAPSED_HEIGHT) {
        eprintln!("notice: 定位失败，沿用默认位置: {error}");
    }
    let _ = app.emit_to(NOTICE_LABEL, NOTICE_EVENT, &payload);
    match window.show() {
        Ok(()) => true,
        Err(error) => {
            eprintln!("notice: 展示失败: {error}");
            false
        }
    }
}

/// 只在状态真的变化时才改窗口样式：切换 WS_EX_NOACTIVATE 会让窗口重绘，
/// 每次点按钮都切一遍看起来就是闪一下。
fn set_focusable(app: &AppHandle<Wry>, window: &WebviewWindow<Wry>, focusable: bool) {
    let changed = app
        .try_state::<NoticeState>()
        .and_then(|state| {
            state.focusable.lock().ok().map(|mut current| {
                if *current == Some(focusable) {
                    false
                } else {
                    *current = Some(focusable);
                    true
                }
            })
        })
        .unwrap_or(true);
    if changed {
        let _ = window.set_focusable(focusable);
    }
}

/// 锚定在工作区右下角，向上生长：展开时底边不动，视觉上从卡片往上长。
fn place(app: &AppHandle<Wry>, window: &WebviewWindow<Wry>, height: f64) -> tauri::Result<()> {
    if let Some(state) = app.try_state::<NoticeState>() {
        if let Ok(mut last) = state.last_height.lock() {
            *last = height;
        }
    }
    window.set_size(LogicalSize::new(WIDTH, height))?;
    let Some(monitor) = app.primary_monitor()? else {
        return Ok(());
    };
    let scale = monitor.scale_factor();
    let area = monitor.work_area();
    let width = (WIDTH * scale).round() as i32;
    let height = (height * scale).round() as i32;
    let margin = (MARGIN * scale).round() as i32;
    let x = area.position.x + area.size.width as i32 - width - margin;
    let y = area.position.y + area.size.height as i32 - height - margin;
    window.set_position(PhysicalPosition::new(x.max(0), y.max(0)))
}

#[tauri::command]
pub fn notice_current(state: State<'_, NoticeState>) -> Option<NoticePayload> {
    state.payload.lock().ok().and_then(|current| current.clone())
}

/// 按页面量出来的卡片高度调整窗口，避免内容被裁掉。
/// 尺寸来自实测而不是写死常量：换行、125% 缩放、字号差异都能自适应。
#[tauri::command]
pub fn notice_resize(
    app: AppHandle<Wry>,
    height: f64,
    focusable: Option<bool>,
) -> Result<(), String> {
    let window = app
        .get_webview_window(NOTICE_LABEL)
        .ok_or_else(|| "notice window is not ready".to_string())?;
    if let Some(focusable) = focusable {
        set_focusable(&app, &window, focusable);
    }
    let height = height.clamp(MIN_HEIGHT, MAX_HEIGHT);
    // 页面每次布局变化都会调这里，高度没变就别动窗口（否则会闪）
    let unchanged = app
        .try_state::<NoticeState>()
        .and_then(|state| state.last_height.lock().ok().map(|last| (*last - height).abs() < 0.5))
        .unwrap_or(false);
    if unchanged {
        return Ok(());
    }
    place(&app, &window, height).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn notice_dismiss(app: AppHandle<Wry>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(NOTICE_LABEL) {
        let _ = window.hide();
    }
    Ok(())
}

/// 主窗口算完动作后把摘要补进通知卡片，通知窗口不再自己请求业务接口。
///
/// 手动触发的干预（点「立即开始活动」）不会经过计时阈值，所以这里发现窗口
/// 还没展示时顺手补一次，和到点提醒走同一套视觉。
#[tauri::command]
pub fn notice_set_action(
    app: AppHandle<Wry>,
    action: NoticeAction,
    minutes: Option<u64>,
) -> Result<(), String> {
    let mut stored = false;
    if let Some(state) = app.try_state::<NoticeState>() {
        if let Ok(mut current) = state.payload.lock() {
            if current.is_none() {
                let sitting = minutes.unwrap_or(0);
                *current = Some(NoticePayload {
                    title: "该起身了".to_string(),
                    body: format!("已经连续久坐 {sitting} 分钟。"),
                    sitting_minutes: sitting,
                    action: Some(action.clone()),
                });
            } else if let Some(payload) = current.as_mut() {
                payload.action = Some(action.clone());
            }
            stored = current.is_some();
        }
    }
    let _ = app.emit_to(NOTICE_LABEL, NOTICE_ACTION_EVENT, &action);
    if stored {
        let visible = app
            .get_webview_window(NOTICE_LABEL)
            .and_then(|window| window.is_visible().ok())
            .unwrap_or(false);
        if !visible {
            reveal(&app);
        }
    }
    Ok(())
}

#[tauri::command]
pub fn notice_start(app: AppHandle<Wry>) -> Result<(), String> {
    focus_main(&app);
    let _ = app.emit_to("main", NOTICE_START_EVENT, ());
    if let Some(window) = app.get_webview_window(NOTICE_LABEL) {
        let _ = window.hide();
    }
    Ok(())
}

#[tauri::command]
pub fn notice_open_main(app: AppHandle<Wry>) -> Result<(), String> {
    focus_main(&app);
    if let Some(window) = app.get_webview_window(NOTICE_LABEL) {
        let _ = window.hide();
    }
    Ok(())
}

fn focus_main(app: &AppHandle<Wry>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}
