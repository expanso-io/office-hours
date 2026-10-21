#!/usr/bin/env bash
# Headless layout check of the cockpit: 4 widths x 2 themes.
# Usage: browser-check.sh OUTDIR
set -euo pipefail
OUT="${1:?outdir}"
mkdir -p "$OUT"
export BROWSER=none
AB=(agent-browser --session oh5-models-check --headed false)
URL="http://127.0.0.1:19500/"
"${AB[@]}" open "$URL" >/dev/null
CHECK='(() => {
  const doc = document.documentElement;
  const inner = [...document.querySelectorAll("body *")].filter((n) => {
    const s = getComputedStyle(n);
    return /(auto|scroll)/.test(s.overflowX + s.overflowY) && (n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1);
  }).map((n) => n.tagName + "." + n.className);
  const fonts = [...new Set([...document.querySelectorAll("body *")].map((n) => getComputedStyle(n).fontFamily))];
  return JSON.stringify({
    theme: doc.dataset.theme,
    width: innerWidth,
    hscroll: doc.scrollWidth > innerWidth,
    inner,
    fonts,
    plexLoaded: document.fonts.check("15px \"IBM Plex Sans\"") && document.fonts.check("13px \"IBM Plex Mono\""),
    records: document.querySelectorAll("#tail tr").length,
  });
})()'
for theme in light dark; do
  for w in 320 400 768 1440; do
    "${AB[@]}" set viewport "$w" 900 >/dev/null
    "${AB[@]}" eval "localStorage.setItem('oh5-theme', '$theme')" >/dev/null
    "${AB[@]}" reload >/dev/null
    sleep 1.5
    "${AB[@]}" eval "$CHECK"
    "${AB[@]}" screenshot --full "$OUT/cockpit-$theme-$w.png" >/dev/null
  done
done
# Toggle persists: click the button in light, reload, expect dark.
"${AB[@]}" eval "localStorage.setItem('oh5-theme', 'light')" >/dev/null
"${AB[@]}" reload >/dev/null
sleep 1
"${AB[@]}" click "#theme" >/dev/null
"${AB[@]}" reload >/dev/null
sleep 1
"${AB[@]}" eval 'JSON.stringify({afterToggleAndReload: document.documentElement.dataset.theme, stored: localStorage.getItem("oh5-theme")})'
"${AB[@]}" close >/dev/null
