// Work page: an exhibition of one work. Photos settle one per screen, a counter follows along,
// arrow keys move between photos, and clicking opens the photo full screen (image only).
import './protect.js';
import { fadeImages, reveal, reducedMotion } from './motion.js';
import PhotoSwipeLightbox from '../vendor/photoswipe/photoswipe-lightbox.esm.min.js';

fadeImages();
reveal(document.querySelectorAll('.reveal'));

const gallery = document.getElementById('gallery');
if (gallery) {
  const lightbox = new PhotoSwipeLightbox({
    gallery,
    children: 'a.plate__link',
    pswpModule: () => import('../vendor/photoswipe/photoswipe.esm.min.js'),
    bgOpacity: 1,
    showHideAnimationType: reducedMotion ? 'none' : 'zoom',
    showAnimationDuration: 450,
    hideAnimationDuration: 400,
    paddingFn: (viewport) => (viewport.x < 700 ? { top: 0, bottom: 0, left: 0, right: 0 } : { top: 40, bottom: 40, left: 40, right: 40 }),
  });
  lightbox.init();
}

const plates = [...document.querySelectorAll('.plate')];
if (plates.length > 1) {
  document.documentElement.classList.add('snap');
  const now = document.querySelector('.counter__now');
  let current = 0;

  // The photo crossing the middle of the screen is the current one.
  const watcher = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      current = plates.indexOf(entry.target);
      if (now) now.textContent = String(current + 1).padStart(2, '0');
    }
  }, { rootMargin: '-50% 0px -50% 0px' });
  plates.forEach((plate) => watcher.observe(plate));

  const go = (step) => {
    const target = plates[Math.min(plates.length - 1, Math.max(0, current + step))];
    target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' });
  };

  document.addEventListener('keydown', (event) => {
    if (document.querySelector('.pswp--open') || event.metaKey || event.ctrlKey || event.altKey) return;
    if (['ArrowDown', 'ArrowRight', 'j'].includes(event.key)) {
      event.preventDefault();
      go(1);
    } else if (['ArrowUp', 'ArrowLeft', 'k'].includes(event.key)) {
      event.preventDefault();
      go(-1);
    }
  });
}
