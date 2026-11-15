//! 动作会话：主窗与通知窗共用同一份状态，倒计时在 Rust 侧推进。
//!
//! 两个 WebView 都可能被隐藏，隐藏时 Chromium 会节流 JS 定时器；
//! 所以计时的真相不放在任何页面里 —— 页面只发命令、只渲染快照。

use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State, Wry};

/// 会话变化广播给所有窗口
pub const ACTION_EVENT: &str = "riseloop://action";
/// 一组动作做完，通知窗据此把主窗唤到前台记录反馈
pub const ACTION_FEEDBACK_EVENT: &str = "riseloop://action-feedback";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ActionStep {
    pub text: String,
    pub seconds: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ActionSnapshot {
    pub loaded: bool,
    /// 动作 id，两个窗口据此取示意图
    #[serde(default)]
    pub id: String,
    pub name: String,
    pub steps: Vec<ActionStep>,
    pub index: usize,
    pub remaining: u32,
    pub running: bool,
    pub done: bool,
}

#[derive(Debug, Default)]
pub struct ActionSession {
    inner: Mutex<ActionSnapshot>,
}

fn step_seconds(step: Option<&ActionStep>) -> u32 {
    step.map(|item| item.seconds.max(1)).unwrap_or(0)
}

impl ActionSession {
    pub fn snapshot(&self) -> ActionSnapshot {
        self.inner
            .lock()
            .map(|current| current.clone())
            .unwrap_or_default()
    }

    /// 换一组动作：先停在第一步、不自动开跑（自动开始由页面按交互时机决定）。
    pub fn load(&self, id: String, name: String, steps: Vec<ActionStep>) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if steps.is_empty() {
            *current = ActionSnapshot::default();
            return current.clone();
        }
        let seconds = step_seconds(steps.first());
        *current = ActionSnapshot {
            loaded: true,
            id,
            name,
            steps,
            index: 0,
            remaining: seconds,
            running: false,
            done: false,
        };
        current.clone()
    }

    pub fn play(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded || current.done || current.remaining == 0 {
            return current.clone();
        }
        current.running = true;
        current.clone()
    }

    pub fn pause(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        current.running = false;
        current.clone()
    }

    /// 同一个按钮切换：跑着就暂停，停着就继续；已经做完则从头再来。
    pub fn toggle(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded {
            return current.clone();
        }
        if current.done {
            current.index = 0;
            current.remaining = step_seconds(current.steps.first());
            current.done = false;
            current.running = true;
        } else {
            current.running = !current.running;
        }
        current.clone()
    }

    pub fn next(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded {
            return current.clone();
        }
        if current.done {
            return current.clone();
        }
        if current.index + 1 < current.steps.len() {
            current.index += 1;
            current.remaining = step_seconds(current.steps.get(current.index));
        } else {
            current.index = current.steps.len().saturating_sub(1);
            current.remaining = 0;
            current.running = false;
            current.done = true;
        }
        current.clone()
    }

    /// 上一步回到该步开头；已经做完时退回最后一步继续。
    pub fn prev(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded {
            return current.clone();
        }
        if current.done {
            current.done = false;
            current.running = false;
            current.index = current.steps.len().saturating_sub(1);
            current.remaining = step_seconds(current.steps.get(current.index));
            return current.clone();
        }
        if current.index == 0 {
            current.remaining = step_seconds(current.steps.first());
            return current.clone();
        }
        current.index -= 1;
        current.remaining = step_seconds(current.steps.get(current.index));
        current.clone()
    }

    /// 从头再来一步不动地回到第一段，并立即开跑。
    pub fn restart(&self) -> ActionSnapshot {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded {
            return current.clone();
        }
        current.index = 0;
        current.remaining = step_seconds(current.steps.first());
        current.done = false;
        current.running = true;
        current.clone()
    }

    /// 每秒推一次；只有真的变了才返回快照，避免无谓广播。
    pub fn tick(&self) -> Option<ActionSnapshot> {
        let mut current = self.inner.lock().expect("action session poisoned");
        if !current.loaded || !current.running || current.done {
            return None;
        }
        if current.remaining > 0 {
            current.remaining -= 1;
        }
        if current.remaining == 0 {
            if current.index + 1 < current.steps.len() {
                current.index += 1;
                current.remaining = step_seconds(current.steps.get(current.index));
            } else {
                current.running = false;
                current.done = true;
            }
        }
        Some(current.clone())
    }
}

fn publish(app: &AppHandle<Wry>, snapshot: &ActionSnapshot) {
    let _ = app.emit(ACTION_EVENT, snapshot);
}

#[tauri::command]
pub fn action_state(session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    session.snapshot()
}

#[tauri::command]
pub fn action_load(
    app: AppHandle<Wry>,
    id: String,
    name: String,
    steps: Vec<ActionStep>,
    session: State<'_, Arc<ActionSession>>,
) -> ActionSnapshot {
    let snapshot = session.load(id, name, steps);
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_play(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.play();
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_pause(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.pause();
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_toggle(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.toggle();
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_next(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.next();
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_prev(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.prev();
    publish(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn action_restart(app: AppHandle<Wry>, session: State<'_, Arc<ActionSession>>) -> ActionSnapshot {
    let snapshot = session.restart();
    publish(&app, &snapshot);
    snapshot
}

/// 做完了：把主窗唤到前台、收起通知窗，并让主窗打开反馈。
#[tauri::command]
pub fn action_finish(app: AppHandle<Wry>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    if let Some(window) = app.get_webview_window(crate::notice::NOTICE_LABEL) {
        let _ = window.hide();
    }
    let _ = app.emit_to("main", ACTION_FEEDBACK_EVENT, ());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn steps() -> Vec<ActionStep> {
        vec![
            ActionStep { text: "第一步".to_string(), seconds: 2 },
            ActionStep { text: "第二步".to_string(), seconds: 3 },
        ]
    }

    #[test]
    fn load_arms_first_step_without_starting() {
        let session = ActionSession::default();
        let snapshot = session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        assert!(snapshot.loaded);
        assert_eq!(snapshot.index, 0);
        assert_eq!(snapshot.remaining, 2);
        assert!(!snapshot.running);
        assert!(!snapshot.done);
    }

    #[test]
    fn tick_advances_into_next_step_and_finishes_at_the_end() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        session.play();
        assert_eq!(session.tick().map(|item| (item.index, item.remaining)), Some((0, 1)));
        // 第一步走到 0 立刻切到第二步
        assert_eq!(session.tick().map(|item| (item.index, item.remaining)), Some((1, 3)));
        session.tick();
        session.tick();
        let snapshot = session.tick().expect("last tick should change state");
        assert!(snapshot.done);
        assert!(!snapshot.running);
        assert_eq!(snapshot.index, 1);
        // 做完之后再 tick 不再广播
        assert!(session.tick().is_none());
    }

    #[test]
    fn paused_session_does_not_tick() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        assert!(session.tick().is_none());
        session.play();
        session.pause();
        assert!(session.tick().is_none());
    }

    #[test]
    fn toggle_restarts_after_finish() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        session.play();
        session.next();
        session.next();
        assert!(session.snapshot().done);
        let snapshot = session.toggle();
        assert!(!snapshot.done);
        assert!(snapshot.running);
        assert_eq!(snapshot.index, 0);
        assert_eq!(snapshot.remaining, 2);
    }

    #[test]
    fn prev_from_done_returns_to_last_step_paused() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        session.play();
        session.next();
        let snapshot = session.next();
        assert!(snapshot.done);
        let back = session.prev();
        assert!(!back.done);
        assert!(!back.running);
        assert_eq!(back.index, 1);
        assert_eq!(back.remaining, 3);
    }

    #[test]
    fn next_keeps_running_state_and_wraps_into_done() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        session.play();
        let second = session.next();
        assert!(second.running);
        assert_eq!(second.index, 1);
        let finished = session.next();
        assert!(finished.done);
    }

    #[test]
    fn empty_steps_clears_the_session() {
        let session = ActionSession::default();
        session.load("s1-stand-break".to_string(), "起身站立".to_string(), steps());
        let cleared = session.load("x".to_string(), "空动作".to_string(), Vec::new());
        assert!(!cleared.loaded);
        assert_eq!(cleared.remaining, 0);
    }
}
