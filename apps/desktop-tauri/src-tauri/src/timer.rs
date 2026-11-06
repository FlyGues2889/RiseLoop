use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;

pub const DEFAULT_THRESHOLD_MINUTES: u64 = 45;
pub const MIN_THRESHOLD_MINUTES: u64 = 30;
pub const MAX_THRESHOLD_MINUTES: u64 = 60;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct TimerSnapshot {
    pub running: bool,
    pub sitting_seconds: u64,
    pub threshold_seconds: u64,
    pub remaining_seconds: u64,
    pub overdue: bool,
    pub threshold_minutes: u64,
}

#[derive(Debug)]
struct Inner {
    running: bool,
    accumulated: Duration,
    started_at: Option<Instant>,
    threshold: Duration,
    notified: bool,
}

#[derive(Debug)]
pub struct SittingTimer {
    inner: Mutex<Inner>,
}

impl SittingTimer {
    pub fn new(threshold_minutes: u64) -> Self {
        let minutes = clamp_threshold(threshold_minutes);
        Self {
            inner: Mutex::new(Inner {
                running: false,
                accumulated: Duration::ZERO,
                started_at: None,
                threshold: Duration::from_secs(minutes * 60),
                notified: false,
            }),
        }
    }

    pub fn start(&self) -> TimerSnapshot {
        let mut inner = self.lock();
        if elapsed(&inner) >= inner.threshold {
            inner.accumulated = Duration::ZERO;
            inner.notified = false;
            inner.started_at = Some(Instant::now());
            inner.running = true;
        } else if !inner.running {
            inner.running = true;
            inner.started_at = Some(Instant::now());
        }
        snapshot(&inner)
    }

    pub fn pause(&self) -> TimerSnapshot {
        let mut inner = self.lock();
        if inner.running {
            let elapsed_since_start = inner.started_at.map(|at| at.elapsed()).unwrap_or_default();
            inner.accumulated += elapsed_since_start;
            inner.started_at = None;
            inner.running = false;
        }
        snapshot(&inner)
    }

    pub fn reset(&self) -> TimerSnapshot {
        let mut inner = self.lock();
        inner.accumulated = Duration::ZERO;
        inner.notified = false;
        inner.started_at = if inner.running {
            Some(Instant::now())
        } else {
            None
        };
        snapshot(&inner)
    }

    /// 仅用于演示：把已累计久坐时间直接推进到指定分钟数。
    pub fn seed_elapsed(&self, minutes: u64) -> TimerSnapshot {
        let mut inner = self.lock();
        inner.accumulated = Duration::from_secs(minutes.saturating_mul(60));
        inner.started_at = if inner.running {
            Some(Instant::now())
        } else {
            None
        };
        inner.notified = false;
        snapshot(&inner)
    }

    pub fn set_threshold(&self, minutes: u64) -> Result<TimerSnapshot, String> {
        if !(MIN_THRESHOLD_MINUTES..=MAX_THRESHOLD_MINUTES).contains(&minutes) {
            return Err(format!(
                "threshold must be between {MIN_THRESHOLD_MINUTES} and {MAX_THRESHOLD_MINUTES} minutes"
            ));
        }
        let mut inner = self.lock();
        inner.threshold = Duration::from_secs(minutes * 60);
        inner.notified = false;
        Ok(snapshot(&inner))
    }

    pub fn snapshot(&self) -> TimerSnapshot {
        snapshot(&self.lock())
    }

    /// 返回 Some 表示本次 tick 刚越过阈值，调用方负责发通知与事件。
    pub fn tick(&self) -> Option<TimerSnapshot> {
        let mut inner = self.lock();
        let elapsed = elapsed(&inner);
        if !inner.running || inner.notified || elapsed < inner.threshold {
            return None;
        }
        inner.notified = true;
        Some(snapshot(&inner))
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

pub fn clamp_threshold(minutes: u64) -> u64 {
    minutes.clamp(MIN_THRESHOLD_MINUTES, MAX_THRESHOLD_MINUTES)
}

fn elapsed(inner: &Inner) -> Duration {
    inner.accumulated
        + inner
            .started_at
            .map(|started| started.elapsed())
            .unwrap_or_default()
}

fn snapshot(inner: &Inner) -> TimerSnapshot {
    let elapsed = elapsed(inner);
    let threshold = inner.threshold;
    TimerSnapshot {
        running: inner.running,
        sitting_seconds: elapsed.as_secs(),
        threshold_seconds: threshold.as_secs(),
        remaining_seconds: threshold.saturating_sub(elapsed).as_secs(),
        overdue: elapsed >= threshold,
        threshold_minutes: threshold.as_secs() / 60,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread::sleep;

    #[test]
    fn starts_paused_and_zeroed() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        let snapshot = timer.snapshot();
        assert!(!snapshot.running);
        assert_eq!(snapshot.sitting_seconds, 0);
        assert_eq!(snapshot.threshold_seconds, 45 * 60);
    }

    #[test]
    fn start_accumulates_while_running_then_pause_freezes() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        sleep(Duration::from_millis(120));
        let running = timer.snapshot();
        assert!(running.running);
        assert!(running.sitting_seconds < 2);

        let paused = timer.pause();
        assert!(!paused.running);
        let frozen = paused.sitting_seconds;
        sleep(Duration::from_millis(120));
        assert_eq!(timer.snapshot().sitting_seconds, frozen);
    }

    #[test]
    fn reset_clears_accumulated_time() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        sleep(Duration::from_millis(30));
        timer.reset();
        let snapshot = timer.snapshot();
        assert!(snapshot.sitting_seconds <= 1);
        assert!(snapshot.remaining_seconds >= 45 * 60 - 2);
    }

    #[test]
    fn tick_fires_once_when_threshold_reached() {
        let timer = SittingTimer::new(MIN_THRESHOLD_MINUTES);
        timer.set_threshold(MIN_THRESHOLD_MINUTES).unwrap();
        {
            let mut inner = timer.lock();
            inner.running = true;
            inner.started_at = Some(Instant::now());
            inner.threshold = Duration::ZERO;
        }
        assert!(timer.tick().is_some(), "首次越过阈值应触发");
        assert!(timer.tick().is_none(), "同一次久坐不应重复触发");

        timer.reset();
        {
            let mut inner = timer.lock();
            inner.threshold = Duration::ZERO;
        }
        assert!(timer.tick().is_some(), "reset 后应允许再次触发");
    }

    #[test]
    fn seed_elapsed_marks_overdue_and_allows_trigger() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        let seeded = timer.seed_elapsed(46);
        assert!(seeded.overdue);
        assert_eq!(seeded.sitting_seconds, 46 * 60);
        assert!(timer.tick().is_some());
    }

    #[test]
    fn start_after_threshold_restarts_a_fresh_round() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        timer.seed_elapsed(DEFAULT_THRESHOLD_MINUTES + 5);
        assert!(timer.snapshot().overdue);

        let restarted = timer.start();
        assert!(restarted.running);
        assert!(!restarted.overdue);
        assert!(restarted.sitting_seconds <= 1);
        assert_eq!(restarted.remaining_seconds, DEFAULT_THRESHOLD_MINUTES * 60);
    }

    #[test]
    fn start_resets_when_triggered_then_paused() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        timer.seed_elapsed(DEFAULT_THRESHOLD_MINUTES + 1);
        assert!(timer.tick().is_some());
        timer.pause();
        assert!(!timer.snapshot().running);

        let restarted = timer.start();
        assert!(restarted.running);
        assert!(!restarted.overdue);
        assert!(restarted.sitting_seconds <= 1);
    }

    #[test]
    fn reset_keeps_running_state_for_resume() {
        let timer = SittingTimer::new(DEFAULT_THRESHOLD_MINUTES);
        timer.start();
        timer.seed_elapsed(20);
        timer.pause();
        assert!(!timer.snapshot().running);
        timer.reset();
        assert!(!timer.snapshot().running, "暂停态 reset 不应自动开始");
        assert_eq!(timer.snapshot().sitting_seconds, 0);
    }

    #[test]
    fn threshold_is_clamped_to_supported_range() {
        assert_eq!(clamp_threshold(10), MIN_THRESHOLD_MINUTES);
        assert_eq!(clamp_threshold(90), MAX_THRESHOLD_MINUTES);
        assert_eq!(clamp_threshold(50), 50);
        assert!(timer_rejects(20));
        assert!(timer_rejects(61));
        assert!(!timer_rejects(45));
    }

    fn timer_rejects(minutes: u64) -> bool {
        SittingTimer::new(DEFAULT_THRESHOLD_MINUTES)
            .set_threshold(minutes)
            .is_err()
    }
}