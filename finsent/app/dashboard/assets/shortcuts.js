// Keyboard shortcuts: "/" focuses company search, 1–7 open the nav pages, P prints, Esc closes popovers.
(function () {
  function typing(target) {
    const tag = (target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
  }

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "Escape") {
      document.querySelectorAll("details[open]").forEach(function (el) { el.removeAttribute("open"); });
      if (document.activeElement) document.activeElement.blur();
      return;
    }
    if (typing(event.target)) return;
    if (event.key === "/") {
      const search = document.querySelector("#global-focus-ticker input");
      if (search) { event.preventDefault(); search.focus(); }
    } else if (/^[1-7]$/.test(event.key)) {
      const links = document.querySelectorAll(".nav-link-item");
      const link = links[Number(event.key) - 1];
      if (link) { event.preventDefault(); link.click(); }
    } else if (event.key === "p" || event.key === "P") {
      event.preventDefault();
      window.print();
    }
  });
})();
