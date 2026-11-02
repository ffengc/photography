// Light deterrents against casual saving: no context menu or dragging on photos.
for (const type of ['contextmenu', 'dragstart']) {
  document.addEventListener(type, (event) => {
    if (event.target instanceof Element && event.target.closest('.gallery, .shots, .pswp')) event.preventDefault();
  });
}
