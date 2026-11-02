// Home page: "Selected" vs "Chronological", large vs small photos (remembered per browser), and the masonry columns.
import './protect.js';
import { fadeImages, reveal } from './motion.js';

const STORAGE_KEY = 'photography:home';
const VIEWS = ['selected', 'timeline'];
const SIZES = ['large', 'small'];
const IMAGE_SIZES = {
  large: '(min-width: 700px) 46vw, 92vw',
  small: '(min-width: 1100px) 24vw, (min-width: 700px) 32vw, 48vw',
};

const main = document.querySelector('main');
const toolbar = document.querySelector('.toolbar');
const grids = [...document.querySelectorAll('.masonry')];

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // storage blocked: the choice isn't remembered
  }
}

const stored = load();
const state = {
  view: VIEWS.includes(stored.view) ? stored.view : 'selected',
  size: SIZES.includes(stored.size) ? stored.size : 'large',
};

// Put each tile into the currently shortest column, so the order still reads roughly left to right.
function layout(grid, force = false) {
  if (grid.closest('[hidden]')) return;
  const cols = parseInt(getComputedStyle(grid).getPropertyValue('--cols'), 10) || 1;
  const key = `${cols}:${state.size}`;
  if (!force && grid.dataset.layout === key) return;
  grid.dataset.layout = key;
  grid.tiles ||= [...grid.querySelectorAll('.tile')];
  const columns = Array.from({ length: cols }, () => Object.assign(document.createElement('div'), { className: 'masonry__col' }));
  const heights = new Array(cols).fill(0);
  const captionHeight = state.size === 'large' ? 0.12 : 0; // caption below each photo, relative to column width
  for (const tile of grid.tiles) {
    if (getComputedStyle(tile).display === 'none') {
      columns[0].append(tile);
      continue;
    }
    const shortest = heights.indexOf(Math.min(...heights));
    columns[shortest].append(tile);
    heights[shortest] += 1 / Number(tile.dataset.ar) + captionHeight;
  }
  grid.replaceChildren(...columns);
  grid.classList.add('is-laid');
}

function apply() {
  for (const section of document.querySelectorAll('section.view')) section.hidden = section.dataset.view !== state.view;
  main.dataset.size = state.size;
  for (const button of toolbar.querySelectorAll('button[data-view]')) button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
  for (const button of toolbar.querySelectorAll('button[data-size]')) button.setAttribute('aria-pressed', String(button.dataset.size === state.size));
  for (const img of document.querySelectorAll('.tile img')) img.sizes = IMAGE_SIZES[state.size];
  for (const grid of grids) layout(grid);
}

if (toolbar) {
  toolbar.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.view) state.view = button.dataset.view;
    if (button.dataset.size) state.size = button.dataset.size;
    save();
    apply();
  });
  toolbar.hidden = false;
}
apply();
fadeImages();
reveal(document.querySelectorAll('.reveal'));

let resizeTimer;
addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => grids.forEach((grid) => layout(grid)), 150);
});

// The clicked photo flies into place on the work page (browsers with cross-document view transitions).
document.addEventListener('click', (event) => {
  const link = event.target.closest('a.tile, a.feature');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  for (const img of document.querySelectorAll('main img')) img.style.viewTransitionName = '';
  link.querySelector('img').style.viewTransitionName = 'photo';
});

// Coming back (back button): clear the name so the next click can use it again.
addEventListener('pageshow', () => {
  for (const img of document.querySelectorAll('main img')) img.style.viewTransitionName = '';
});
