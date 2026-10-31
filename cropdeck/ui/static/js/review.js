// The review's keys (handoff phase 6): J/K next and previous card, Enter accept, E edit,
// Space true size. Ignored while typing in a field, except Enter (accepts the card, as its form
// submits) and Esc (leaves the field). The true-size dialog shows the selected card.
(() => {
  const dialog = document.getElementById("true-size");
  let selectedId = null;

  const cards = () => [...document.querySelectorAll(".review-card")];
  const selected = () => (selectedId && document.getElementById(selectedId)) || cards()[0] || null;

  function select(card, focus = true) {
    if (!card) return;
    cards().forEach((c) => c.removeAttribute("data-selected"));
    card.setAttribute("data-selected", "");
    selectedId = card.id;
    if (focus) {
      card.focus({ preventScroll: true });
      card.scrollIntoView({ block: "nearest" });
    }
  }

  function move(step) {
    const all = cards();
    const at = all.indexOf(selected());
    const next = all[at + step];
    if (next) select(next);
    return next || null;
  }

  function show(card) {
    if (!card) return;
    dialog.querySelector("h2").textContent = card.dataset.title;
    const badge = card.querySelector(".badge");
    dialog.querySelector(".true-size-badge").replaceChildren(badge ? badge.cloneNode(true) : "");
    for (const side of ["front", "back"]) {
      const img = dialog.querySelector(`img[data-side="${side}"]`);
      if (card.dataset[side]) img.src = card.dataset[side];
      else img.removeAttribute("src");
    }
    if (!dialog.open) dialog.showModal();
  }

  function accept(card) {
    const form = card && card.querySelector("form");
    if (form) form.requestSubmit();
  }

  select(selected(), false);

  document.addEventListener("focusin", (event) => {
    const card = event.target.closest(".review-card");
    if (card && card.id !== selectedId) select(card, false);
  });

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-true-size]");
    if (opener) {
      select(opener.closest(".review-card"), false);
      show(selected());
      return;
    }
    const go = event.target.closest("[data-go]");
    if (go) {
      show(move(Number(go.dataset.go)) || selected());
      return;
    }
    if (event.target.closest("[data-accept-next]")) {
      accept(selected());
      const next = move(1);
      if (next) show(next);
      else dialog.close();
    }
  });

  // an accepted card comes back from the server as a new element: keep it selected
  document.addEventListener("htmx:afterSwap", () => {
    const card = selectedId && document.getElementById(selectedId);
    if (card && !card.hasAttribute("data-selected")) {
      card.setAttribute("data-selected", "");
      if (!dialog.open && !document.activeElement.closest(".review-card")) card.focus({ preventScroll: true });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey || dialog.open) return;
    const target = event.target instanceof Element ? event.target : document.body;
    if (target.matches("input, textarea, select")) {
      if (event.key === "Escape") {
        target.blur(); // the field saves as it is left
        select(target.closest(".review-card"));
      }
      return; // Enter submits the card's form by itself: accept
    }
    if (target.matches("button, a") && (event.key === "Enter" || event.key === " ")) return;
    const key = event.key.toLowerCase();
    if (key === "j") move(1);
    else if (key === "k") move(-1);
    else if (key === "enter") accept(selected());
    else if (key === "e") {
      const field = selected() && selected().querySelector("input");
      if (field) {
        field.focus();
        field.select();
      }
    } else if (key === " ") show(selected());
    else return;
    event.preventDefault();
  });
})();
