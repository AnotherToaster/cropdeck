// cropdeck's own few lines of script; everything else is htmx.
// A button with data-copy puts that text on the clipboard and says so on itself.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button || !navigator.clipboard) return;
  navigator.clipboard.writeText(button.dataset.copy).then(() => {
    const label = button.querySelector("span");
    if (label && button.dataset.copied) label.textContent = button.dataset.copied;
  });
});
