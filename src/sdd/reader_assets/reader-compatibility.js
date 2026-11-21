(() => {
  const data = JSON.parse(document.querySelector('[data-reader-compatibility]').textContent);
  const hash = location.hash.slice(1);
  let decoded;
  try {
    decoded = decodeURIComponent(hash);
  } catch {
    decoded = hash;
  }
  if (!hash) {
    if (data.page) location.replace(data.page);
  } else {
    const fragments = data.fragments;
    const key = Object.hasOwn(fragments, hash) ? hash : decoded;
    if (Object.hasOwn(fragments, key)) location.replace(fragments[key]);
  }
})();
