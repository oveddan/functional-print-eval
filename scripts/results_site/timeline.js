// A trial's timeline: its phases in order (what it asked, the test prints it asked for, each design and what the
// person said between them) as a row of tabs. Picking a phase tells the page to show that phase's version in the
// stage below; the chosen phase is kept in the URL as phase=<key>.
//
// The phases come from the trial's own data (`timeline`, written by scripts/results_site_timeline.py). Nothing is
// counted here except the checks at the bottom, which compare each label's number with the trial's own lists.

import { h, add, clear, icon, badge, VERDICT } from "./util.js";

const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- the URL ----

export function phaseInUrl(slug) {
  const params = new URLSearchParams(location.search);
  return params.get("trial") === slug ? params.get("phase") || "" : "";
}

// Replaces the address, never adds a history entry: Back still leaves the trial, however many phases were looked at.
export function writePhase(slug, key) {
  const url = new URL(location.href);
  if (url.searchParams.get("trial") !== slug) return;
  if (key) url.searchParams.set("phase", key);
  else url.searchParams.delete("phase");
  history.replaceState(history.state, "", url.pathname + url.search + url.hash);
}

// ---- the control ----

// The phase a trial opens on: its own design (the first print on a first print's page, the second on a second's).
export function ownPhase(phases, slug) {
  const own = phases.filter((phase) => phase.slug === slug);
  return own.filter((phase) => phase.kind === "design").pop() || own.pop() || phases[phases.length - 1];
}

function dotOf(phase, at) {
  const verdict = phase.kind === "design" ? VERDICT[phase.verdict] : null;
  return h("span", { class: "tl-dot", "aria-hidden": "true" }, verdict ? icon(verdict.icon) : String(at + 1));
}

// phases: the trial's timeline. onSelect(phase) draws that phase into the panel. Returns { el, panel, select }.
export function timelineControl(phases, slug, onSelect) {
  const id = (key) => `tl-tab-${key}`;
  const panel = h("div", { class: "tl-panel", id: "tl-panel", role: "tabpanel" });
  const steps = h("div", { class: "tl-steps", role: "tablist", "aria-label": "Timeline of this trial: pick a phase to see that version", "aria-orientation": "horizontal" });
  const now = h("div", { class: "tl-now" });
  const earlier = h("button", { type: "button", class: "btn btn-small tl-move" }, icon("prev"), "Earlier");
  const later = h("button", { type: "button", class: "btn btn-small tl-move" }, "Later", icon("next"));
  let current = -1;

  const tabs = phases.map((phase, at) => {
    const verdict = phase.kind === "design" ? VERDICT[phase.verdict] : null;
    const tab = h("button", {
      type: "button", role: "tab", id: id(phase.key), class: `tl-step tl-${phase.kind}${verdict ? ` ${verdict.cls}` : ""}`,
      "aria-selected": "false", "aria-controls": "tl-panel", tabindex: "-1", title: phase.line,
    }, dotOf(phase, at), h("span", { class: "tl-label" }, phase.label));
    tab.addEventListener("click", () => select(at, { user: true }));
    return tab;
  });

  const select = (at, { user = false, focus = false } = {}) => {
    if (at < 0 || at >= phases.length) return;
    const changed = at !== current;
    current = at;
    const phase = phases[at];
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === at));
      tab.tabIndex = i === at ? 0 : -1;
      tab.classList.toggle("tl-before", i <= at);
    });
    if (focus) tabs[at].focus({ preventScroll: true });
    // Keep the chosen step in view inside the strip, without moving the page.
    const tab = tabs[at];
    steps.scrollTo({ left: tab.offsetLeft - (steps.clientWidth - tab.offsetWidth) / 2, behavior: calm() ? "auto" : "smooth" });
    earlier.disabled = at === 0;
    later.disabled = at === phases.length - 1;
    panel.setAttribute("aria-labelledby", id(phase.key));
    add(clear(now),
      h("p", { class: "tl-now-title" },
        h("span", { class: "tl-count" }, `Step ${at + 1} of ${phases.length}`),
        h("strong", {}, phase.kind === "design" ? phase.label.split(": ")[0] : phase.label),
        phase.kind === "design" ? badge(phase.verdict, { small: true }) : null),
      h("p", { class: "tl-now-line" }, phase.line));
    if (user) writePhase(slug, phase === ownPhase(phases, slug) ? "" : phase.key);
    if (changed) onSelect(phase, now);
  };

  steps.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const to = { ArrowLeft: current - 1, ArrowUp: current - 1, ArrowRight: current + 1, ArrowDown: current + 1, Home: 0, End: phases.length - 1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    event.stopPropagation();  // the dialog's own arrow keys step between trials
    select(Math.max(0, Math.min(phases.length - 1, to)), { user: true, focus: true });
  });
  earlier.addEventListener("click", () => select(current - 1, { user: true }));
  later.addEventListener("click", () => select(current + 1, { user: true }));

  add(steps, tabs);
  const el = h("section", { class: "tl", "aria-label": "Timeline" },
    h("div", { class: "tl-head" }, h("h3", {}, "Timeline"), h("p", { class: "tl-hint" }, "Pick a step to see that version below. The sections after it stay with this trial.")),
    steps,
    h("div", { class: "tl-foot" }, now, h("div", { class: "tl-moves" }, earlier, later)));
  return {
    el, panel,
    start(key) {
      const at = phases.findIndex((phase) => phase.key === key);
      select(at >= 0 ? at : phases.indexOf(ownPhase(phases, slug)));
      // The strip has no width until it's in the page: centre the chosen step once it has.
      requestAnimationFrame(() => { const tab = tabs[current]; steps.scrollLeft = tab.offsetLeft - (steps.clientWidth - tab.offsetWidth) / 2; });
    },
  };
}

// ---- the page's own check: every number a timeline label carries agrees with the trial's own lists ----

export function timelineProblems(detail) {
  const phases = detail.timeline || [];
  const own = phases.filter((phase) => phase.slug === detail.slug);
  const problems = [];
  const same = (label, mine, theirs) => { if (mine !== theirs) problems.push(`${detail.id} timeline ${label}: the timeline says ${mine}, the trial's data says ${theirs}`); };
  if (new Set(phases.map((phase) => phase.key)).size !== phases.length) problems.push(`${detail.id} timeline: two phases share a key`);
  const asked = own.filter((phase) => phase.kind === "asked");
  same("measurements asked", asked.reduce((sum, phase) => sum + phase.count, 0), (detail.measures || []).length);
  for (const phase of asked) same(`“${phase.label}”`, Number(phase.label.match(/\d+/)?.[0]), phase.count);
  const rounds = own.filter((phase) => phase.kind === "round");
  same("test-print rounds", rounds.length, (detail.test_prints || []).length);
  for (const phase of rounds) same(`round ${phase.round} pieces`, phase.pieces, detail.test_prints?.[phase.round - 1]?.parts.length);
  const design = own.filter((phase) => phase.kind === "design");
  same("designs of this trial", design.length, 1);
  if (design.length) same("verdict", design[0].verdict, detail.verdict);
  for (const phase of phases) if (phase.kind === "design" && !phase.label.endsWith(`: ${phase.verdict}`)) problems.push(`${detail.id} timeline: “${phase.label}” doesn't state its verdict, ${phase.verdict}`);
  return problems;
}
