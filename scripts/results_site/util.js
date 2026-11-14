// Small helpers shared by the page's modules: DOM building, verdict vocabulary, URL slugs and number formats.
// Everything from the data files goes into the page as text nodes, never as HTML.

const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  add(el, kids);
  return el;
}

export function add(el, ...kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false || kid === "") continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

// ---- icons: one shape per verdict, so colour is never the only signal ----

const ICON_PATHS = {
  check: '<path d="M3.2 8.6l3.1 3.1 6.5-7.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  cross: '<path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  question: '<path d="M5.4 6.1a2.7 2.7 0 1 1 3.9 2.4c-.8.4-1.3.9-1.3 1.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="12.9" r="1.1" fill="currentColor"/>',
  minus: '<path d="M3.5 8h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  empty: '<circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M4.4 11.6l7.2-7.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  bang: '<path d="M8 3v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="8" cy="12.4" r="1.2" fill="currentColor"/>',
  close: '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  prev: '<path d="M10 3L5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  next: '<path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  link: '<path d="M6.8 9.2a2.6 2.6 0 0 0 3.7 0l2-2a2.6 2.6 0 0 0-3.7-3.7l-.7.7M9.2 6.8a2.6 2.6 0 0 0-3.7 0l-2 2a2.6 2.6 0 0 0 3.7 3.7l.7-.7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  cube: '<path d="M8 1.8l5.4 3.1v6.2L8 14.2l-5.4-3.1V4.9zM8 8l5.4-3.1M8 8L2.6 4.9M8 8v6.2" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>',
  out: '<path d="M6.5 3.5H3.5v9h9v-3M9 3.5h3.5V7M12.5 3.5L7.5 8.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  skip: '<path d="M3 4l4 4-4 4M8 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  zoom: '<circle cx="7" cy="7" r="4.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.2 10.2L13.5 13.5M5.2 7h3.6M7 5.2v3.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  filter: '<path d="M2 4h12M4.5 8h7M7 12h2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  arrow: '<path d="M3 8h9M8.5 4.5L12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
};

export function icon(name, cls = "icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.innerHTML = ICON_PATHS[name] || "";  // static strings from this file only
  return svg;
}

// ---- verdicts ----

export const VERDICTS = ["pass", "fail", "not graded", "declined", "no design", "error"];
export const CHECK_STATES = ["fail", "not graded", "not reached", "pass"];

export const VERDICT = {
  "pass": { slug: "pass", label: "Pass", cls: "v-pass", icon: "check" },
  "fail": { slug: "fail", label: "Fail", cls: "v-fail", icon: "cross" },
  "not graded": { slug: "not-graded", label: "Not graded", cls: "v-ng", icon: "question" },
  "declined": { slug: "declined", label: "Declined", cls: "v-other", icon: "minus" },
  "no design": { slug: "no-design", label: "No design", cls: "v-other", icon: "empty" },
  "error": { slug: "error", label: "Error", cls: "v-other", icon: "bang" },
  // a check's state only, never a trial's verdict: an earlier failure blocked this check
  "not reached": { slug: "not-reached", label: "Not reached", cls: "v-nr", icon: "skip" },
};

export const ISSUE_VERDICT = { "failed": "fail", "not graded": "not graded", "declined": "declined", "no design": "no design", "error": "error" };

export function verdictFromSlug(slug) {
  return VERDICTS.find((verdict) => VERDICT[verdict].slug === slug) || "";
}

export function badge(verdict, { small = false, label = null } = {}) {
  const meta = VERDICT[verdict] || VERDICT.error;
  return h("span", { class: `badge ${meta.cls}${small ? " badge-small" : ""}` }, icon(meta.icon), h("span", {}, label || meta.label));
}

// A finding's ok is true, false or null (not graded).
export function okVerdict(ok) {
  return ok === true ? "pass" : ok === false ? "fail" : "not graded";
}

// ---- URL slugs ----

const TASK_SLUGS = { "nut-knob/M3": "knob-m3", "nut-knob/M5": "knob-m5" };
export const TASK_ORDER = ["tripod-plate", "bearing-wheel", "nut-knob/M3", "nut-knob/M5", "estoa-light", "m5-spacer"];

export const taskSlug = (task) => TASK_SLUGS[task] || task;
export const taskFromSlug = (slug) => Object.keys(TASK_SLUGS).find((task) => TASK_SLUGS[task] === slug) || slug;
const COND_SLUGS = { test_first: "test-first", after_feedback: "after-feedback" };
export const condSlug = (group) => COND_SLUGS[group] || group;
export const condFromSlug = (slug) => Object.keys(COND_SLUGS).find((group) => COND_SLUGS[group] === slug) || slug;
export const modelSlug = (model) => model.split("/").pop();

export function slugify(text) {
  return String(text).toLowerCase().replace(/`/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

// ---- text ----

// Reason strings carry markdown backticks (and the Estoa sentence carries **bold** and one link): show code as code.
export function rich(text) {
  const out = [];
  const plain = String(text ?? "").replace(/\s*\(\[[^\]]*\]\(#[^)]*\)\)/g, "").replace(/\[([^\]]*)\]\(#[^)]*\)/g, "$1");
  for (const [i, piece] of plain.split("`").entries()) {
    if (i % 2) { out.push(h("code", {}, piece)); continue; }
    for (const [j, part] of piece.split("**").entries()) out.push(j % 2 ? h("strong", {}, part) : part);
  }
  return out;
}

export const plainText = (text) => String(text ?? "").replace(/`/g, "");

// Prose from the data that still says "coupon" for a test print (ids and saved model text are left alone).
export const reader = (text) => String(text ?? "").replace(/\bcoupons\b/g, "test prints").replace(/\bcoupon\b/g, "test print");

// ---- numbers: formatting only, never arithmetic that could disagree with the data ----

export function money(usd) {
  if (usd === null || usd === undefined) return "n/a";
  if (usd === 0) return "$0";
  return "$" + (usd < 0.01 ? usd.toFixed(4) : usd < 1 ? usd.toFixed(3) : usd.toFixed(2));
}

export const money2 = (usd) => (usd === null || usd === undefined ? "n/a" : "$" + usd.toFixed(2));
export const pct = (rate) => Math.round(100 * rate) + "%";
export const int = (n) => (n === null || n === undefined ? "n/a" : Math.round(n).toLocaleString("en-US"));

export function tokens(n) {
  if (n === null || n === undefined) return "n/a";
  return n >= 10000 ? (n / 1000).toFixed(1) + "k" : int(n);
}

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "n/a";
  if (seconds < 90) return Math.round(seconds) + " s";
  if (seconds < 3600) return Math.round(seconds / 60) + " min";
  return (seconds / 3600).toFixed(1) + " h";
}

export const hours = (seconds) => (seconds === null || seconds === undefined ? "n/a" : (seconds / 3600).toFixed(1) + " h");
export const grams = (g) => (g === null || g === undefined ? "n/a" : (g < 10 ? g.toFixed(1) : Math.round(g)) + " g");

// "0.4 h", always one decimal: for per-pass estimates that sit in a column
export const hours1 = (seconds) => (seconds === null || seconds === undefined ? "n/a" : (seconds / 3600).toFixed(1) + " h");
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;

export function dateOnly(iso) {
  return iso ? String(iso).slice(0, 10) : "n/a";
}

export function copyButton(getText, label = "Copy") {
  const button = h("button", { type: "button", class: "btn btn-quiet btn-small" }, label);
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(getText());
      button.textContent = "Copied";
    } catch {
      button.textContent = "Couldn't copy";
    }
    setTimeout(() => { button.textContent = label; }, 1600);
  });
  return button;
}
