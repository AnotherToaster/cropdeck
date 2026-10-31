// Setup's folder browser: "Use this folder" puts the folder into the field (which then updates
// the scans path below it), and the close button hides the browser again.
document.addEventListener("click", (event) => {
  const use = event.target.closest("[data-use]");
  const close = event.target.closest("[data-close-browser]");
  if (!use && !close) return;
  if (use) {
    const field = document.getElementById("folder");
    field.value = use.dataset.use;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  document.getElementById("browser").hidden = true;
});

