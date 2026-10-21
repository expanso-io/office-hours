// Apply the remembered theme before the page paints. Light unless the
// viewer chose dark on an earlier visit.

function storedTheme() {
  try {
    return localStorage.getItem("oh5-theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

document.documentElement.dataset.theme = storedTheme();
