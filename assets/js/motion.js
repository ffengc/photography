// Shared motion: photos fade in once loaded, and blocks rise in as they scroll into view.
window.__motion = true;

export const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

export function fadeImages(scope = document) {
  for (const img of scope.querySelectorAll('img.fade:not(.is-loaded)')) {
    if (img.complete && img.naturalWidth) img.classList.add('is-loaded');
    else img.addEventListener('load', () => img.classList.add('is-loaded'), { once: true });
  }
}

const observer = reducedMotion || !('IntersectionObserver' in window)
  ? null
  : new IntersectionObserver((entries) => {
    let delay = 0;
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.style.setProperty('--delay', `${Math.min(delay, 360)}ms`);
      entry.target.classList.add('is-in');
      observer.unobserve(entry.target);
      delay += 80; // blocks that appear together come in one after another
    }
  }, { rootMargin: '0px 0px -6% 0px' });

export function reveal(nodes) {
  for (const node of nodes) {
    if (observer) observer.observe(node);
    else node.classList.add('is-in');
  }
}
