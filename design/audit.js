// Проверка вёрстки: вставить в консоль страницы (или выполнить через инструменты браузера).
// Раскрывает все <details>, ищет горизонтальную прокрутку и элементы, вылезающие за родителя или за экран.
(() => {
  document.querySelectorAll("details").forEach((d) => (d.open = true));
  const vw = document.documentElement.clientWidth;
  const problems = [];
  const name = (el) =>
    el.tagName.toLowerCase() +
    (el.id ? `#${el.id}` : "") +
    (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : "");
  const visible = (el) => {
    const s = getComputedStyle(el);
    return s.display !== "none" && s.visibility !== "hidden" && el.getClientRects().length;
  };
  for (const el of document.body.querySelectorAll("*")) {
    if (!visible(el) || el.closest(".hp, .skip-link, script, style, option, select")) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > vw + 1 || r.left < -1) {
      problems.push(`за экраном: ${name(el)} [${Math.round(r.left)}..${Math.round(r.right)}] при ширине ${vw}`);
      continue;
    }
    const parent = el.parentElement;
    if (!parent || parent === document.body) continue;
    const ps = getComputedStyle(parent);
    if (/(auto|scroll|hidden|clip)/.test(ps.overflowX)) continue;
    const pr = parent.getBoundingClientRect();
    const padR = parseFloat(ps.paddingRight) || 0;
    if (r.right > pr.right - padR + 2 && r.right > pr.right + 1) {
      problems.push(`вылезает из родителя: ${name(el)} → ${name(parent)} на ${Math.round(r.right - pr.right)}px`);
    }
  }
  const sw = document.documentElement.scrollWidth;
  if (sw > vw) problems.unshift(`горизонтальная прокрутка: ${sw} > ${vw}`);
  return { width: vw, problems: [...new Set(problems)].slice(0, 25) };
})();
