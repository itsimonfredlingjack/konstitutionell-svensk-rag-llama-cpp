/** Pipeline step-through animation interval (ms) */
export const STEP_TIMER_MS = 420;

/** Grading stage watchdog — advance to generation if grading stalls (ms) */
export const GRADING_WATCHDOG_MS = 2000;

/** Default minimum visual duration per pipeline stage transition (ms) */
export const MIN_STAGE_DURATION_MS = 500;

/** Delay after metadata arrives before advancing to grading stage (ms) */
export const METADATA_STAGE_DELAY_MS = 600;

/** Delay after grading/thought-chain before advancing stage (ms) */
export const GRADING_STAGE_DELAY_MS = 400;

/** Maximum pipeline log entries kept in memory */
export const MAX_PIPELINE_LOG_ENTRIES = 50;

/** Maximum query history entries */
export const MAX_QUERY_HISTORY = 12;

/** Scroll throttle interval during streaming (ms) */
export const SCROLL_THROTTLE_MS = 150;

/** Distance from bottom threshold for auto-scroll (px) */
export const SCROLL_NEAR_BOTTOM_PX = 100;
