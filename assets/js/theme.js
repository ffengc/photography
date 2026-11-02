// Color theme: Auto (by local time, light 7:00–19:00), Light or Dark. The choice is remembered per browser.
const STORAGE_KEY = 'photography:theme';
const MODES = ['auto', 'light', 'dark'];
const LABELS = { auto: 'Auto', light: 'Light', dark: 'Dark' };

const root = document.documentElement;
const button = document.querySelector('.theme-toggle');

const byTime = () => {
  const hour = new Date().getHours();
  return hour >= 7 && hour < 19 ? 'light' : 'dark';
};

let mode = MODES.includes(root.dataset.themeMode) ? root.dataset.themeMode : 'auto';

function apply() {
  root.dataset.themeMode = mode;
  root.dataset.theme = mode === 'auto' ? byTime() : mode;
  if (!button) return;
  button.dataset.mode = mode;
  button.querySelector('.theme-toggle__label').textContent = LABELS[mode];
  button.title = mode === 'auto' ? 'Theme follows the time of day. Click for light.' : `Theme: ${LABELS[mode]}. Click to change.`;
}

if (button) {
  button.hidden = false;
  button.addEventListener('click', () => {
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    apply();
  });
}
apply();

// In Auto mode, follow the clock if the page stays open past 7:00 or 19:00.
setInterval(() => {
  if (mode === 'auto') apply();
}, 60 * 1000);
