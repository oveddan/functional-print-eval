// The results site: the finding, the scorecard, the trial browser and its URL state. One trial's detail is in
// detail.js and the 3D viewer in viewer.js; both load their data only when a trial is opened.
//
// Loading order: data/scorecard.json (5 KB gzipped) paints the finding and the scorecard; data/index.json fills the
// reasons chart and the trials; a ?trial= link fetches that trial's own file alongside, without waiting for the index.
//
// URL (all optional, in the query string):
//   cond    first | after-feedback | test-first | second | <another group's key>          default first
//           after-feedback: every first print, counted as the scorecard's "after feedback" column counts it
//           (the first print if it passed or wasn't replayed, otherwise its second print)
//   task    tripod-plate | bearing-wheel | knob-m3 | knob-m5 | estoa-light | m5-spacer | scored | all    default all
//   verdict pass | fail | not-graded | declined | no-design | error | not-counted
//           didnt-pass (fail, declined or no design together) | second-pass (after-feedback only: passes on the
//           second print): the scorecard chart's pieces link with these two
//   model   the model id after its slash, e.g. gemini-4-argon; or run-all-three-ways (the models in the headline);
//           or sent-back (those of them whose first prints were sent back when they didn't pass)
//   reason  a reason group's key, e.g. holed-roof or a-tripod-head-recess-under-5-mm-deep
//   show    pictures | strips     overrides the automatic choice between picture cards and one line per model
//   trial   a trial's slug: opens that trial

import {
  h, add, clear, icon, badge, VERDICTS, VERDICT, ISSUE_VERDICT, verdictFromSlug, TASK_ORDER,
  taskSlug, taskFromSlug, condSlug, condFromSlug, modelSlug, slugify, pct, money2, hours1, grams, tokens, plural,
} from "./util.js";
import { renderDetail, renderDetailShell, updateShell, teardown } from "./detail.js";
import { timelineProblems } from "./timeline.js";

const $ = (id) => document.getElementById(id);
const ROWS_PER_BATCH = 8;       // model rows put in the page at a time
const STRIPS_ABOVE = 150;       // more trials than this and each model gets one line, not a row of pictures
const POOLED = "pooled";        // the model filter's value for "the models run in all three ways"
const POOLED_SLUG = "run-all-three-ways";
const FED = "fed";              // the headline's models whose failed first prints were sent back: the after-feedback headline
const FED_SLUG = "sent-back";
const DEFAULTS = { cond: "first", task: "all", verdict: "", model: "", reason: "", show: "", trial: "" };
const COND = {
  first: { short: "First print", noun: "first prints" },
  after_feedback: { short: "After feedback", noun: "first prints, counted after one round of feedback" },
  test_first: { short: "Test prints first", noun: "trials that could ask for test prints first" },
  second: { short: "Second prints", noun: "second prints" },
};
const AFTER_GROUP = {
  key: "after_feedback", label: "After one round of feedback", kind: "headline", category: "headline",
  description: "Every first print, counted the way the scorecard's after-feedback column counts it: a first print that passed counts as it is; one that didn't was sent back once, with the simulated person saying how it came out, and its second print counts instead. Models that weren't replayed keep their first prints.",
};
const CATEGORY_LABEL = { "control or pilot": "Controls and pilots", "infrastructure check": "Infrastructure checks", "replay study": "Replay studies" };
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const phone = matchMedia("(max-width: 760px)");  // where the scorecard table and the by-part panels fold away
// A reason as a reader sees it: without the grader's own id on the end, "… cut through it (bridges)".
const readerReason = (text) => String(text ?? "").replace(/ \([a-z][a-z0-9_]*\)$/, "");

let card = null;    // data/scorecard.json
let index = null;   // data/index.json
const state = { ...DEFAULTS };
const lookup = {
  bySlug: new Map(), byId: new Map(), groups: new Map(), entries: new Map(), modelBySlug: new Map(), modelOrder: [],
  reasonAlias: new Map(), reasonKind: new Map(),
};
const details = new Map();    // slug -> promise of the trial's detail
const linkChecks = new Map();  // every scorecard link, with the numbers its cell shows: checked once the index is in
let notices = [];             // what the URL asked for that doesn't exist
let shown = [];               // the entries the current filters show, in page order
let pending = [];             // model rows not yet in the page
let sentinelWatch = null;
let closingFromCode = false;
let dialogSlug = null;
let earlyDetail = null;       // a deep-linked trial's detail, fetched before the index
let countProblems = [];       // what verifyCounts found, kept apart from the list's own check
let listCheck = { links: 0, problems: [] };  // the links in the trial list now on the page

// ---- data ----

async function getJson(path) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function useScorecard(data) {
  card = data;
  const score = data.scorecard;
  const ranked = [...score.test_first_order, ...score.not_tested_order];
  lookup.modelOrder = [...ranked, ...Object.keys(data.models).filter((model) => !ranked.includes(model)).sort()];
  for (const model of lookup.modelOrder) lookup.modelBySlug.set(modelSlug(model), model);
}

function useIndex(data) {
  index = data;
  if (!card) useScorecard({ scorecard: data.scorecard, definitions: data.definitions, tasks: data.tasks, models: data.models, notes: data.notes, groups: data.groups });
  for (const group of data.groups) lookup.groups.set(group.key, group);
  lookup.groups.set(AFTER_GROUP.key, AFTER_GROUP);
  for (const group of lookup.groups.keys()) lookup.entries.set(group, []);
  for (const row of data.trials) {
    lookup.bySlug.set(row.slug, row);
    lookup.byId.set(row.id, row);
    row.reasons = [...new Set(row.issues.map((issue) => issue.reason_group))];
    for (const issue of row.issues) {
      lookup.reasonAlias.set(slugify(issue.reason), issue.reason_group);  // links written against the v1 reason text
      lookup.reasonKind.set(issue.reason_group, issue.reason_kind);
    }
    lookup.entries.get(row.group).push({ row, verdict: row.verdict, counted: row.counted });
  }
  for (const key of Object.keys(data.reason_groups)) lookup.reasonAlias.set(key, key);
  // After feedback: one entry per counted first print, pointing at the print whose verdict counts.
  for (const { row } of lookup.entries.get("first")) {
    const after = row.after_feedback;
    if (!after?.counted) continue;
    const second = after.via === "second" && after.second_slug ? lookup.bySlug.get(after.second_slug) : null;
    lookup.entries.get(AFTER_GROUP.key).push({ row: second || row, first: row, verdict: after.verdict, counted: true, via: second ? "second" : "first", replayed: after.replayed });
  }
  AFTER_GROUP.trials = lookup.entries.get(AFTER_GROUP.key).length;
}

// Every failing or not-graded check in a loaded trial says where to see it: a drawing, or the reason there is none.
const detailCheck = { details: 0, checks: 0, problems: [] };
function verifyDetail(detail) {
  detailCheck.details += 1;
  for (const finding of detail.findings || []) {
    if (finding.state !== "fail" && finding.state !== "not graded") continue;
    detailCheck.checks += 1;
    const drawn = finding.view && typeof finding.view.url === "string" && finding.view.caption;
    if (!drawn && !finding.no_view_reason) detailCheck.problems.push(`${detail.id} ${finding.check} on ${finding.part}: neither a drawing nor a reason for none`);
  }
  detailCheck.problems.push(...timelineProblems(detail));  // a timeline label's number against the trial's own lists
  if (detailCheck.problems.length) console.error("Detail check: a failing check has neither a drawing nor a reason", detailCheck.problems.slice(-1)[0]);
  if (window.resultsSiteCheck) window.resultsSiteCheck.detail = detailCheck;
  return detail;
}

export function fetchDetail(slug) {
  if (!details.has(slug)) {
    const promise = getJson(`data/trials/${encodeURIComponent(slug)}.json`).then(verifyDetail);
    promise.catch(() => details.delete(slug));
    details.set(slug, promise);
  }
  return details.get(slug);
}

const meta = () => index || card;
const isHeadline = (cond = state.cond) => lookup.groups.get(cond)?.kind === "headline";
const taskLabel = (task) => meta().tasks[task]?.label || task;
const taskShort = (task) => meta().tasks[task]?.short || task;
const modelShort = (model) => meta().models[model]?.short || model;
const modelRank = (model) => { const at = lookup.modelOrder.indexOf(model); return at < 0 ? 999 : at; };
const pooledModels = () => card.scorecard.pooled.model_ids;
const fedModels = () => card.scorecard.pooled.after_feedback.model_ids;
const modelSet = (model) => (model === POOLED ? pooledModels() : model === FED ? fedModels() : null);
const modelSetLabel = (model) => (model === POOLED ? `the ${pooledModels().length} models run all three ways`
  : `the ${fedModels().length} headline models whose failed first prints were sent back`);
const taskMatches = (row, task) => task === "all" || (task === "scored" ? meta().tasks[row.task].scored : row.task === task);
const modelMatches = (row, model) => !model || (modelSet(model) ? modelSet(model).includes(row.model) : row.model === model);
const condShort = (cond) => COND[cond]?.short || lookup.groups.get(cond)?.label || cond;

// ---- URL state ----

const ECHO_MAX = 40;  // how much of an unrecognised URL value the page repeats back

function readUrl() {
  const params = new URLSearchParams(location.search);
  const next = { ...DEFAULTS };
  notices = [];
  // A link can carry any text in a parameter; the notice repeats only its first few characters, as text.
  const unknown = (name, value) => notices.push(`${name} “${value.length > ECHO_MAX ? `${value.slice(0, ECHO_MAX)}…` : value}”`);
  const trial = params.get("trial");
  if (trial) { if (lookup.bySlug.has(trial)) next.trial = trial; else unknown("trial", trial); }
  const condParam = params.get("cond");
  const cond = condFromSlug(condParam || "");
  if (lookup.groups.has(cond)) next.cond = cond;
  else {
    if (condParam) unknown("condition", condParam);
    if (next.trial) next.cond = lookup.bySlug.get(next.trial).group;  // a bare trial link opens over its own list
  }
  const taskParam = params.get("task");
  const task = taskFromSlug(taskParam || "");
  if (index.tasks[task] || task === "scored" || task === "all") next.task = task;
  else if (taskParam) unknown("part", taskParam);
  const verdict = params.get("verdict");
  if (verdict === "not-counted" || VERDICT_SETS[verdict] || verdictFromSlug(verdict)) next.verdict = verdict;
  else if (verdict) unknown("verdict", verdict);
  const model = params.get("model");
  if (model === POOLED_SLUG) next.model = POOLED;
  else if (model === FED_SLUG) next.model = FED;
  else if (lookup.modelBySlug.has(model)) next.model = lookup.modelBySlug.get(model);
  else if (model) unknown("model", model);
  const reason = params.get("reason");
  if (lookup.reasonAlias.has(reason)) next.reason = lookup.reasonAlias.get(reason);
  else if (reason) unknown("reason", reason);
  const show = params.get("show");
  if (show === "pictures" || show === "strips") next.show = show;
  else if (show) unknown("show", show);
  Object.assign(state, next);
  normalise();
  if (notices.length) history.replaceState(history.state, "", hrefFor());  // the address bar shows what is really applied
}

export function hrefFor(patch = {}, base = state) {
  const next = { ...base, ...patch };
  const params = new URLSearchParams();
  if (next.cond !== DEFAULTS.cond) params.set("cond", condSlug(next.cond));
  if (next.task !== DEFAULTS.task) params.set("task", taskSlug(next.task));
  if (next.verdict) params.set("verdict", next.verdict);
  if (next.model) params.set("model", next.model === POOLED ? POOLED_SLUG : next.model === FED ? FED_SLUG : modelSlug(next.model));
  if (next.reason) params.set("reason", next.reason);
  if (next.show) params.set("show", next.show);
  if (next.trial) params.set("trial", next.trial);
  const query = params.toString();
  return location.pathname + (query ? "?" + query : "");
}

// A link to a list, from anywhere: starts from the defaults, not from the filters now set.
const listHref = (patch) => hrefFor(patch, DEFAULTS);

function navigate(patch, { replace = false, toResults = false, fromDefaults = false, opened = false, stay = false } = {}) {
  const openingTrial = "trial" in patch;
  if (!openingTrial) notices = [];
  Object.assign(state, fromDefaults ? DEFAULTS : {}, patch);
  if (!openingTrial && !("show" in patch)) state.show = fromDefaults ? "" : state.show;
  normalise();
  const url = hrefFor();
  if (replace) history.replaceState(history.state, "", url);
  else history.pushState(opened ? { trialOpened: true } : null, "", url);
  render();
  if (toResults) scrollToResults(true);
  else if (!openingTrial && !stay && $("results-top").getBoundingClientRect().top < 0) scrollToResults(false);
}

// A filter set from inside the list. The list above the clicked row changes length (rows drop out, the reason's
// picture comes in, the row's own reasons reorder), so the page is scrolled by exactly that much: the control that
// was clicked stays under the cursor and keeps the focus.
function navigateInPlace(patch, rowKey, focusSelector) {
  const findRow = () => document.querySelector(`#results [data-row="${CSS.escape(rowKey)}"]`);
  const find = () => { const row = findRow(); return row && (row.querySelector(focusSelector) || row.querySelector("a, button")); };
  const before = find()?.getBoundingClientRect().top;
  navigate(patch, { stay: true });
  let guard = 0;
  while (pending.length && !findRow() && guard++ < 200) renderResults.batch();
  const control = find();
  if (!control || before === undefined) { scrollToResults(true); return; }
  scrollBy({ top: control.getBoundingClientRect().top - before, behavior: "instant" });
  control.focus({ preventScroll: true });
}

// Keep the filters consistent with the chosen condition: a part or model with no entries there falls back to "all".
function normalise() {
  const inGroup = lookup.entries.get(state.cond) || [];
  if (state.task !== "all" && !inGroup.some((entry) => taskMatches(entry.row, state.task))) state.task = "all";
  if (state.task === "scored" && inGroup.every((entry) => taskMatches(entry.row, "scored"))) state.task = "all";
  if (state.model && !inGroup.some((entry) => modelMatches(entry.row, state.model))) state.model = "";
  if (state.verdict === "not-counted" && (!isHeadline() || !inGroup.some((entry) => !entry.counted))) state.verdict = "";
  if (VERDICT_SETS[state.verdict] && !VERDICT_SETS[state.verdict].applies(state.cond)) state.verdict = "";
}

function scrollToResults(focus) {
  const target = $("results-top");
  target.scrollIntoView({ behavior: reducedMotion() || !focus ? "auto" : "smooth", block: "start" });
  if (focus) target.focus({ preventScroll: true });
}

// A control that re-drew the list is usually gone afterwards: the focus goes to what took its place, never to the
// top of the page.
const refocus = (selector) => (document.querySelector(selector) || $("results-top")).focus({ preventScroll: true });

const plainClick = (event) => !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0);

// A link that changes the list without loading the page again; modified clicks still open a new tab. Before the
// index has loaded the link works as an ordinary link.
function stateLink(patch, attrs, kids, options = {}) {
  const link = h("a", { href: options.fromDefaults ? listHref(patch) : hrefFor(patch), ...attrs }, kids);
  link.addEventListener("click", (event) => {
    if (!plainClick(event) || !index) return;
    event.preventDefault();
    navigate(patch, options);
    if (!link.isConnected && !options.toResults) $("results-top").focus({ preventScroll: true });
  });
  return link;
}

// A scorecard link: goes to the cards, and is remembered so its numbers can be checked against the list it opens.
function cellLink(label, patch, expect, attrs, kids) {
  linkChecks.set(label, { label, patch, ...expect });
  return stateLink(patch, attrs, kids, { fromDefaults: true, toResults: true });
}

// ---- filtering ----

function scopeEntries(s, { task = true, model = true } = {}) {
  return (lookup.entries.get(s.cond) || []).filter((entry) => (!task || taskMatches(entry.row, s.task)) && (!model || modelMatches(entry.row, s.model)));
}

// Verdict filter values that aren't one verdict. The scorecard chart links with them, so each piece of a bar opens
// exactly the designs it counts.
const VERDICT_SETS = {
  "didnt-pass": { label: "Didn't pass", title: "Fail, declined or no design. Not graded is counted apart.", applies: () => true,
    match: (entry, cond) => countable(entry, cond) && !["pass", "not graded", "error"].includes(entry.verdict) },
  "second-pass": { label: "Pass on the second print", title: "First prints that didn't pass and whose second print, after feedback, passes.", applies: (cond) => cond === "after_feedback",
    match: (entry) => entry.verdict === "pass" && entry.via === "second" },
};

function verdictMatches(entry, s) {
  if (VERDICT_SETS[s.verdict]) return VERDICT_SETS[s.verdict].match(entry, s.cond);
  if (!isHeadline(s.cond)) return !s.verdict || VERDICT[entry.verdict].slug === s.verdict;
  if (s.verdict === "not-counted") return !entry.counted;
  return entry.counted && (!s.verdict || VERDICT[entry.verdict].slug === s.verdict);
}

const reasonMatches = (entry, s) => !s.reason || entry.row.reasons.includes(s.reason);
const selectEntries = (s) => scopeEntries(s).filter((entry) => verdictMatches(entry, s) && reasonMatches(entry, s));
const countable = (entry, cond = state.cond) => !isHeadline(cond) || entry.counted;

function sortEntries(entries) {
  const taskRank = (task) => { const at = TASK_ORDER.indexOf(task); return at < 0 ? 99 : at; };
  return entries.sort((a, b) => taskRank(a.row.task) - taskRank(b.row.task) || modelRank(a.row.model) - modelRank(b.row.model) ||
    a.row.trial - b.row.trial || a.row.id.localeCompare(b.row.id));
}

function countVerdicts(entries) {
  const counts = {};
  for (const entry of entries) counts[entry.verdict] = (counts[entry.verdict] || 0) + 1;
  return counts;
}

const verdictLine = (counts) => VERDICTS.filter((verdict) => counts[verdict]).map((verdict) => `${counts[verdict]} ${VERDICT[verdict].label.toLowerCase()}`).join(", ");

// The reason groups among some entries, most common first. A trial counts once per group.
function reasonCounts(entries) {
  const found = new Map();
  for (const entry of entries) {
    for (const key of entry.row.reasons) {
      if (!found.has(key)) found.set(key, { key, text: index.reason_groups[key] || key, kind: lookup.reasonKind.get(key), count: 0 });
      found.get(key).count += 1;
    }
  }
  return [...found.values()].sort((a, b) => b.count - a.count || a.text.localeCompare(b.text));
}

// ---- the finding ----

// What the after-feedback number counts. It is not every headline model: a model whose first prints were never sent
// back has no after-feedback result, so the rate is the others', beside those same models' first-print rate.
function fedNote(pooled) {
  const after = pooled.after_feedback;
  const left = after.not_sent_back;
  const which = left.length ? `${after.models} of the ${pooled.models} models` : "the same models";
  const sentence = `${which}: each first print that didn't pass was sent back once. Their first prints alone: ${pct(after.first.rate)} (${after.first.passes} of ${after.first.trials}).`;
  return left.length ? `${sentence} ${left.join(" and ")}'s first prints weren't sent back.` : sentence;
}

function renderFinding() {
  const score = card.scorecard;
  const pooled = score.pooled;
  const tell = score.cant_tell;
  const tile = (key, cond, label, note, model = POOLED) => {
    const cell = pooled[key];
    return cellLink(`headline ${key}`, { cond, task: "scored", model }, { trials: cell.trials, passes: cell.passes }, { class: "stat" }, [
      h("span", { class: "stat-rate" }, pct(cell.rate)),
      h("span", { class: "stat-label" }, label),
      h("span", { class: "stat-frac" }, `${cell.passes} of ${cell.trials}`),
      note ? h("span", { class: "stat-note" }, note) : null,
    ]);
  };
  const heading = $("finding");
  add(clear(heading),
    tile("first", "first", "on the first print", null),
    tile("after_feedback", "after_feedback", "after one round of feedback", fedNote(pooled), FED),
    tile("test_first", "test_first", "asking for test prints first", `fewer trials ran; in ${tell.told} of ${tell.trials} the person couldn't say how a test piece came out`));
  heading.removeAttribute("aria-busy");
  $("kicker").textContent = `${pooled.models} language models were asked, in a person's own words, for a part to 3D print. Of their designs, this many pass:`;

  const definitions = card.definitions;
  const term = (name, body) => h("div", {}, h("dt", {}, body), h("dd", {}, definitions[name]));
  add(clear($("legend-body")),
    VERDICTS.map((verdict) => term(verdict, badge(verdict, { small: true }))),
    term("not reached", badge("not reached", { small: true })),
    term("not counted", h("span", { class: "tag tag-excluded" }, "Not counted")),
    term("test print", h("b", {}, "Test print")),
    term("simulated person", h("b", {}, "The person")),
    term("Dan", h("b", {}, "Dan")),
    term("cost per passing design", h("b", {}, "Cost per passing design")),
    term("print time and filament", h("b", {}, "Print time and filament")));
}

// The hero's "See a failing design": a first print of a scored part that fails, with its failing region marked.
function wireFailingExample() {
  const firsts = lookup.entries.get("first").map((entry) => entry.row).filter((row) => row.verdict === "fail" && row.thumb && row.thumb_role === "final");
  const pick = firsts.find((row) => row.issues.length === 1 && row.issues[0].reason_group === "holed-roof" && row.task === "tripod-plate" && row.views > 0) || firsts[0];
  if (!pick) return;
  for (const link of [$("see-failing"), $("hero-example")]) {
    link.href = listHref({ task: pick.task, verdict: "fail", trial: pick.slug });
    link.addEventListener("click", (event) => {
      if (!plainClick(event)) return;
      event.preventDefault();
      navigate({ task: pick.task, verdict: "fail", trial: pick.slug }, { fromDefaults: true, opened: true });
    });
  }
  const image = h("img", { src: pick.thumb, alt: "", width: "640", height: "512", decoding: "async" });
  image.addEventListener("error", () => image.remove());
  $("hero-thumb").replaceChildren(image);
  $("hero-cap").textContent = `One failing design (${pick.model_short}, ${taskLabel(pick.task)}, trial ${pick.trial}): ${readerReason(pick.issues[0].reason)}, marked in red. Open it.`;
  $("jump-trials").addEventListener("click", (event) => { if (plainClick(event)) { event.preventDefault(); scrollToResults(true); } });
}

// ---- why first prints don't pass ----

// A reason's picture: Dan's photo of a recorded print where there is one, else a check's drawing of one design.
function whyThumb(key) {
  const picture = index.reason_pictures?.[key];
  if (!picture) return h("span", { class: "why-thumb why-thumb-none", "aria-hidden": "true" });
  const image = h("img", { src: picture.thumb, alt: "", decoding: "async", width: "96", height: "72" });
  const box = h("span", { class: `why-thumb${picture.kind === "drawing" ? " why-thumb-drawing" : ""}`, "aria-hidden": "true" }, image);
  image.addEventListener("error", () => box.classList.add("why-thumb-none"), { once: true });
  return box;
}

// What the picture is, in words a reader sees without hovering: whose it is, and that a design wasn't printed.
const pictureKind = (picture) => (picture.kind === "drawing" ? "Picture: the check's drawing of one design (not printed)"
  : picture.kind === "test print" ? "Picture: one of Dan's test prints" : "Picture: from Dan's own build");

function whyTag(key) {
  const picture = index.reason_pictures?.[key];
  return picture ? h("small", { class: "why-tag" }, pictureKind(picture)) : null;
}

function renderWhy() {
  const entries = lookup.entries.get("first").filter((entry) => entry.counted);
  const notPassing = entries.filter((entry) => entry.verdict !== "pass").length;
  const reasons = reasonCounts(entries).filter((reason) => reason.kind === "failed" || reason.kind === "not graded").slice(0, 8);
  const most = Math.max(...reasons.map((reason) => reason.count), 1);
  const models = new Set(entries.map((entry) => entry.row.model)).size;
  $("why-sub").textContent = `Across every model's first prints (all ${models} models, not only the ${pooledModels().length} in the numbers above), ${notPassing} of ${entries.length} don't pass. These are the most common reasons, by number of designs; a design can have more than one. Each opens the designs behind it.`;
  const list = clear($("why-body"));
  for (const reason of reasons) {
    const verdict = ISSUE_VERDICT[reason.kind];
    list.append(h("li", {}, cellLink(`why ${reason.key}`, { reason: reason.key }, { trials: reason.count }, { class: `why-row ${VERDICT[verdict].cls}` }, [
      whyThumb(reason.key),
      h("span", { class: "why-label" }, icon(VERDICT[verdict].icon), h("span", { class: "why-words" }, h("span", { class: "why-text" }, reason.text), whyTag(reason.key))),
      h("span", { class: "why-track", "aria-hidden": "true" }, h("span", { class: `why-bar${verdict === "not graded" ? " why-bar-ng" : ""}`, style: `width:${(100 * reason.count / most).toFixed(1)}%` })),
      h("span", { class: "why-n" }, String(reason.count), h("span", { class: "sr-only" }, ` designs, ${VERDICT[verdict].label.toLowerCase()}`)),
    ])));
  }
  list.removeAttribute("aria-busy");
}

// ---- scorecard ----

// One bar, the same size everywhere: passes, then not graded (hatched), then everything else.
function bar(cell, { split = false } = {}) {
  if (!cell || !cell.trials) return null;
  const el = h("span", { class: "bar", "aria-hidden": "true" });
  const seg = (cls, n) => { if (n > 0) el.append(h("span", { class: cls, style: `flex-grow:${n}` })); };
  if (split) { seg("bar-pass", cell.passed_first); seg("bar-pass2", cell.passed_after_feedback); }
  else seg("bar-pass", cell.passes);
  seg("bar-ng", cell.not_graded || 0);
  seg("bar-rest", cell.trials - cell.passes - (cell.not_graded || 0));
  return el;
}

function stoppedNote(excluded) {
  if (!excluded?.count) return null;
  const why = excluded.by_reason.map((item) => item.reason.replace(/^infrastructure error, not a result: /, "")).join("; ");
  return h("span", { class: "cell-note" }, `${excluded.count} more stopped and aren't counted: ${why}`);
}

// A model's name, linked to its trials the way the chart's names are.
function modelLink(entry, where) {
  return cellLink(`${entry.short}, name in the ${where}`, { model: entry.model }, { atLeast: 1 },
    { class: "name-link", "aria-label": `${entry.short}: open this model's trials` }, entry.short);
}

// On a phone the chart above already shows every model, so what repeats them is folded away until asked for.
function phoneFold(id, label, kids) {
  return h("details", { id, class: "phone-fold", open: !phone.matches }, h("summary", {}, label), kids);
}

// A link to a folded part (#scorecard-table, #by-task) opens it.
function openTargetedFold() {
  let target = null;
  try { target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { return; }
  const fold = target?.closest(".phone-fold") || (target?.matches("section") ? target.querySelector(":scope > .phone-fold") : null);
  if (!fold || fold.open) return;
  fold.open = true;
  target.scrollIntoView({ block: "start" });
}

function renderScorecard() {
  const score = card.scorecard;
  const byModel = new Map(score.models.map((entry) => [entry.model, entry]));
  const tell = score.cant_tell;
  const table = h("table", { class: "score" },
    h("caption", { class: "sr-only" }, "Pass rate on the four scored parts, per model and condition"),
    h("thead", {}, h("tr", {},
      h("th", { scope: "col" }, "Model"),
      h("th", { scope: "col" }, "First print", h("small", {}, "can ask for measurements, no test prints")),
      h("th", { scope: "col" }, "After one round of feedback", h("small", {}, "passes first time, plus second prints that pass")),
      h("th", { scope: "col", "aria-sort": "descending" }, "Test prints first ", h("span", { class: "sort-mark", title: "Sorted by this column, highest first" }, "▼"),
        h("small", {}, `the person couldn't say how a test piece came out in ${tell.told} of ${tell.trials} trials; ${tell.passes_after_cant_tell} of the ${tell.passes} passes came after such an answer`)),
      h("th", { scope: "col", class: "num" }, "Per passing design, with test prints first", h("small", {}, "API cost; print time and filament are slicer estimates, nothing was printed")))));
  const body = h("tbody", {});
  const rate = (label, cell, patch, extra) => cellLink(label, patch, { trials: cell.trials, passes: cell.passes },
    { class: "cell", "aria-label": `${label}: ${pct(cell.rate)}, ${cell.passes} of ${cell.trials} pass. Open these ${cell.trials} trials.` },
    [h("span", { class: "rate" }, pct(cell.rate)), h("span", { class: "frac" }, `${cell.passes} of ${cell.trials}`), bar(cell, extra)]);

  for (const model of lookup.modelOrder.filter((id) => byModel.has(id))) {
    const entry = byModel.get(model);
    if (model === score.not_tested_order[0]) {
      body.append(h("tr", { class: "divider" }, h("th", { colspan: "5", scope: "colgroup" }, "Not run with test prints, by first-print pass rate")));
    }
    const after = entry.after_feedback;
    const afterCell = entry.replayed
      ? [rate(`${entry.short}, after feedback`, after, { cond: "after_feedback", task: "scored", model }, { split: true }),
        h("span", { class: "cell-note" }, `${after.passed_first} first time, ${after.passed_after_feedback} after feedback`)]
      : h("span", { class: "cell-none" }, "No second prints were run for this model");
    const test = entry.test_first;
    const testCell = test
      ? [rate(`${entry.short}, test prints first`, test, { cond: "test_first", task: "scored", model }),
        stoppedNote(test.excluded),
        h("span", { class: "cell-note" }, `the person couldn't tell in ${test.cant_tell.trials} of ${test.trials}`)]
      : h("span", { class: "cell-none" }, "Not run with test prints");
    const per = test
      ? h("span", { class: "per" }, h("span", { class: "per-cost" }, money2(test.cost_per_pass)), h("span", {}, `est. ${hours1(test.est_print_s_per_pass)} printing`), h("span", {}, `est. ${grams(test.est_grams_per_pass)} filament`))
      : h("span", { class: "cell-none" }, "n/a");
    body.append(h("tr", {},
      h("th", { scope: "row" }, modelLink(entry, "table"), h("small", {}, `${tokens(entry.tokens_per_trial)} tokens a trial`)),
      h("td", { "data-label": "First print" }, rate(`${entry.short}, first print`, entry.first, { cond: "first", task: "scored", model }), stoppedNote(entry.first.excluded)),
      h("td", { "data-label": "After one round of feedback" }, afterCell),
      h("td", { "data-label": "Test prints first" }, testCell),
      h("td", { "data-label": "Per passing design, with test prints first (est.)", class: "td-per num" }, per)));
  }
  table.append(body);

  const estoa = score.estoa_line.replace(/\*\*/g, "").replace(/\s*\(\[[^\]]*\]\(#[^)]*\)\)/g, "").replace(/1 of 30 designs pass/, "1 of 30 designs passes");
  const notes = h("div", { class: "notes" },
    h("p", { class: "bar-legend" },
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-pass" })), "pass"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-pass2" })), "pass on the second print"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-ng" })), "not graded (never a pass)"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-rest" })), "didn't pass (fail, declined or no design)")),
    h("p", {}, "Sorted by pass rate with test prints first, then lower cost per passing design; the models not run that way follow, by first-print pass rate. ",
      `Models need ${score.min_trials} or more trials on each part to be listed with test prints. A cell's total is the number of trials saved for that model, which isn't always 40. ${score.skipped}`),
    h("p", {}, "The three columns aren't a ranking of methods: the test-prints-first column has fewer trials, and a pass after “I can't tell you how that one came out” may owe something to the model moving to a size the records cover."),
    h("p", {}, estoa, " ",
      stateLink({ cond: "first", task: score.harder_task }, {}, "First prints", { fromDefaults: true, toResults: true }), ", ",
      stateLink({ cond: "after_feedback", task: score.harder_task }, {}, "after feedback", { fromDefaults: true, toResults: true }), ", ",
      stateLink({ cond: "test_first", task: score.harder_task }, {}, "with test prints first", { fromDefaults: true, toResults: true }), "."));

  const host = $("scorecard-body");
  add(clear(host), renderScorecardChart(), h("h3", { class: "sc-table-h" }, "All three conditions, as a table"),
    phoneFold("scorecard-table", `The table: ${plural(byModel.size, "model")}, all three conditions`, [h("div", { class: "table-scroll" }, table), notes]));
  host.removeAttribute("aria-busy");
}

// ---- scorecard chart: one stacked bar per model, the first print and then one round of feedback ----

const SHOW_COUNT_FROM = 0.06;  // a segment narrower than this share of its bar has no number on it (the line under it does)
const FEW_PASSES = 5;          // a cost per passing design from fewer passes than this is shown muted, with the count
const COST_LABEL = "API cost per passing design, first print plus feedback";
const chartChecks = [];        // the numbers each chart row draws, checked against the trials once the index is in

// The headline's models whose failed first prints were sent back, added up from their own rows.
function pooledChartCell(score) {
  const rows = score.models.filter((entry) => score.pooled.after_feedback.model_ids.includes(entry.model)).map((entry) => entry.after_feedback);
  const sum = (key) => rows.reduce((total, cell) => total + cell[key], 0);
  const cell = { trials: sum("trials"), passes: sum("passes"), passed_first: sum("passed_first"), passed_after_feedback: sum("passed_after_feedback"), not_graded: sum("not_graded"), cost_usd: sum("cost_usd") };
  return { ...cell, rate: cell.passes / cell.trials, cost_per_pass: cell.passes ? cell.cost_usd / cell.passes : null };
}

function chartCost(cell) {
  const label = h("span", { class: "sc-cost-label" }, COST_LABEL, ": ");
  if (cell.cost_per_pass === null || cell.cost_per_pass === undefined) return h("span", { class: "sc-cost" }, label, h("span", { class: "sc-cost-none" }, "no passing design, so no value"));
  const few = cell.passes < FEW_PASSES;
  return h("span", { class: `sc-cost${few ? " sc-cost-few" : ""}` }, label, h("b", {}, money2(cell.cost_per_pass)),
    h("small", {}, few ? `from ${plural(cell.passes, "pass", "passes")}, ${money2(cell.cost_usd)} in all` : `${money2(cell.cost_usd)} over ${cell.passes} passes`));
}

// One row: the model, a bar whose length is the share of its counted designs that pass (first print, then the second
// print after feedback), that share as a number, and what a passing design cost. The designs that didn't pass or
// weren't graded are not drawn as bar: they are counted in the line under it, each count opening its designs.
function chartRow({ name, model, cell, note, pooled = false }) {
  const rest = cell.trials - cell.passes - cell.not_graded;
  const scope = { task: "scored", model };
  const share = (n) => pct(n / cell.trials);
  const segments = [
    { cls: "bar-pass", n: cell.passed_first, text: share(cell.passed_first), said: `${share(cell.passed_first)} passed on the first print (${cell.passed_first} of ${cell.trials})`,
      line: `${cell.passed_first} on the first print`, patch: { cond: "first", verdict: "pass" }, passes: cell.passed_first, drawn: true },
    { cls: "bar-pass2", n: cell.passed_after_feedback, text: `+${share(cell.passed_after_feedback)}`, said: `${share(cell.passed_after_feedback)} more passed on the second print, after feedback (${cell.passed_after_feedback} of ${cell.trials})`,
      line: `${cell.passed_after_feedback} more after feedback`, patch: { cond: "after_feedback", verdict: "second-pass" }, passes: cell.passed_after_feedback, drawn: true },
    { cls: "bar-ng", n: cell.not_graded, said: `${cell.not_graded} not graded, never counted as a pass`,
      line: `${cell.not_graded} not graded`, patch: { cond: "after_feedback", verdict: "not-graded" }, passes: 0 },
    { cls: "bar-rest", n: rest, said: `${rest} didn't pass: failed, declined or handed in no design`,
      line: `${rest} didn't pass`, patch: { cond: "after_feedback", verdict: "didnt-pass" }, passes: 0 },
  ].filter((segment) => segment.n > 0);
  chartChecks.push({ name, model, trials: cell.trials, first: cell.passed_first, second: cell.passed_after_feedback, notGraded: cell.not_graded, rest, cost: cell.cost_usd, perPass: cell.cost_per_pass,
    pieces: segments.map((segment) => ({ what: segment.line, n: segment.n, patch: { ...scope, ...segment.patch } })) });
  const opens = (segment) => `Opens ${segment.n === 1 ? "it" : `those ${segment.n}`}.`;
  const bar = h("span", { class: "sc-bar" }, segments.filter((segment) => segment.drawn).map((segment) => {
    const said = `${name}: ${segment.said}. ${opens(segment)}`;
    return cellLink(`chart, ${name}, ${segment.cls}`, { ...scope, ...segment.patch }, { trials: segment.n, passes: segment.passes },
      { class: `sc-seg ${segment.cls}`, style: `width:${(100 * segment.n / cell.trials).toFixed(3)}%`, "aria-label": said, title: said },
      segment.n / cell.trials >= SHOW_COUNT_FROM ? h("span", { class: "sc-n", "aria-hidden": "true" }, segment.text) : null);
  }));
  const total = cellLink(`chart, ${name}, after feedback`, { ...scope, cond: "after_feedback" }, { trials: cell.trials, passes: cell.passes },
    { class: "sc-total", "aria-label": `${name}, after one round of feedback: ${pct(cell.rate)}, ${cell.passes} of ${cell.trials} pass. Open these ${cell.trials} designs.` },
    [h("span", { class: "rate" }, pct(cell.rate)), h("span", { class: "frac" }, `${cell.passes} of ${cell.trials}`)]);
  const title = stateLink({ model }, { class: "sc-name", "aria-label": `${name}: open ${pooled ? "these models'" : "this model's"} trials` }, name, { fromDefaults: true, toResults: true });
  // The counts behind the percentages. Each opens its designs: the two that aren't bar have no other way in, and a
  // thin piece of bar (one pass of 40) is too narrow to tap, so its count is the way in on a touch screen.
  const counts = segments.map((segment) => cellLink(`chart count, ${name}, ${segment.cls}`, { ...scope, ...segment.patch }, { trials: segment.n, passes: segment.passes },
    { class: `sc-count${segment.cls === "bar-ng" ? " sc-count-ng" : ""}`, "aria-label": `${name}: ${segment.said}${segment.drawn ? "" : `, of ${cell.trials} counted designs`}. ${opens(segment)}` }, segment.line));
  const line = h("span", { class: "sc-line" }, counts.flatMap((item, at) => (at ? [h("span", { class: "sc-sep", "aria-hidden": "true" }, ", "), item] : [item])),
    note ? h("span", { class: "sc-note" }, `; ${note}`) : null);
  return h("li", { class: `sc-row${pooled ? " sc-row-pooled" : ""}` }, title, bar, total, line, chartCost(cell));
}

function renderScorecardChart() {
  const score = card.scorecard;
  chartChecks.length = 0;
  const row = (entry) => chartRow({ name: entry.short, model: entry.model, cell: entry.after_feedback });
  // score.models comes sorted by pass rate after feedback, then lower cost; without second prints that is the first print's
  const replayed = score.models.filter((entry) => entry.replayed).sort((a, b) => b.after_feedback.rate - a.after_feedback.rate);
  const firstOnly = score.models.filter((entry) => !entry.replayed).sort((a, b) => b.first.rate - a.first.rate);
  const pooledFirstOnly = firstOnly.filter((entry) => score.pooled.model_ids.includes(entry.model)).length;
  const rows = [
    replayed.map(row),
    firstOnly.length ? h("li", { class: "sc-divider" }, "First print only: no second prints were run") : null,
    firstOnly.map(row),
    chartRow({ name: `Headline, ${score.pooled.after_feedback.models} models`, model: FED, cell: pooledChartCell(score), pooled: true,
      note: `the ${score.pooled.after_feedback.models} headline models whose failed first prints were sent back${pooledFirstOnly ? `; ${score.pooled.after_feedback.not_sent_back.join(" and ")}, first print only, is left out` : ""}` }),
  ];
  const key = (cls, label) => h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: cls })), label);
  return h("section", { class: "sc-chart", "aria-labelledby": "sc-chart-h" },
    h("div", { class: "sc-head" },
      h("h3", { id: "sc-chart-h" }, "First print, then one round of feedback"),
      h("p", {}, "The length of each bar is the share of a model's counted designs, for the four scored parts, that pass. A first print that didn't pass was sent back once, with the simulated person saying how it came out, and its second print counts instead. Each piece of a bar, and each count under it, opens exactly the designs it counts."),
      h("p", { class: "sc-order" }, "Sorted by pass rate after feedback, highest first", firstOnly.length ? "; the models with no second prints follow, by first-print pass rate." : ".")),
    h("p", { class: "bar-legend sc-legend" },
      key("bar-pass", "pass on the first print"), key("bar-pass2", "pass on the second print, after feedback (+)"),
      h("span", { class: "key" }, "Not graded is never a pass, so it is no part of a bar; it is counted under each one, with the designs that didn't pass.")),
    h("div", { class: "sc-axis", "aria-hidden": "true" },
      h("span", {}, "Model"),
      h("span", { class: "sc-ticks" }, [0, 25, 50, 75, 100].map((tick) => h("span", { style: `left:${tick}%` }, `${tick}%`))),
      h("span", {}, "Pass after feedback"),
      h("span", { class: "sc-axis-cost" }, COST_LABEL)),
    h("p", { class: "sc-cost-note" }, `The dollar figure in each row is the ${COST_LABEL}.`),
    h("ul", { class: "sc-rows" }, rows),
    h("p", { class: "sc-foot" }, `${COST_LABEL}: what the API provider charged for every first print in the bar, plus each second print that is counted in it, divided by the number of designs that pass after feedback; where no second prints were run it is the first prints' cost over the first prints that pass. A value from fewer than ${FEW_PASSES} passes is shown muted, with the number of passes: one more or one fewer pass would move it a lot. A model with no passing design would have no value, not zero. Print time and filament aren't in it, and nothing a model designed was printed. The table's cost column is for the runs with test prints first, a different condition, so its figures differ.`));
}

// The chart's numbers against the trials, counted by the page's own filtering.
function verifyChart(same) {
  for (const drawn of chartChecks) {
    const list = selectEntries({ ...DEFAULTS, cond: "after_feedback", task: "scored", model: drawn.model });
    const passes = list.filter((item) => item.verdict === "pass");
    const notGraded = list.filter((item) => item.verdict === "not graded").length;
    const spend = list.reduce((total, item) => total + item.first.cost_usd + (item.via === "second" ? item.row.cost_usd : 0), 0);
    same(`chart ${drawn.name} designs`, list.length, drawn.trials);
    same(`chart ${drawn.name} passed on the first print`, passes.filter((item) => item.via === "first").length, drawn.first);
    same(`chart ${drawn.name} passed on the second print`, passes.filter((item) => item.via === "second").length, drawn.second);
    same(`chart ${drawn.name} not graded`, notGraded, drawn.notGraded);
    same(`chart ${drawn.name} the rest`, list.length - passes.length - notGraded, drawn.rest);
    same(`chart ${drawn.name} API cost in cents`, Math.round(spend * 100), Math.round(drawn.cost * 100));
    same(`chart ${drawn.name} cost per passing design`, passes.length ? money2(spend / passes.length) : null, drawn.perPass === null || drawn.perPass === undefined ? null : money2(drawn.perPass));
    // each piece of the bar opens a list of exactly as many designs as the piece counts, and the pieces make the bar
    for (const piece of drawn.pieces) same(`chart ${drawn.name} link “${piece.what}” opens`, selectEntries({ ...DEFAULTS, ...piece.patch }).length, piece.n);
    same(`chart ${drawn.name} pieces add up`, drawn.pieces.reduce((total, piece) => total + piece.n, 0), drawn.trials);
  }
  const headline = chartChecks.find((drawn) => drawn.model === FED);
  const pooled = index.scorecard.pooled;
  same("chart headline first-print passes", headline.first, pooled.after_feedback.first.passes);
  same("chart headline passes after feedback", headline.first + headline.second, pooled.after_feedback.passes);
  same("chart headline designs", headline.trials, pooled.after_feedback.trials);
}

// ---- small multiples: one panel per model, parts down, the three conditions across ----

const MULTI_CONDS = [["first", "First", "first"], ["after_feedback", "After feedback", "after_feedback"], ["test_first", "Test prints first", "test_first"]];

// The Estoa box has no per-model block in the scorecard for first print and after feedback: counted from the rows.
function harderCell(cond, model, task) {
  if (!index) return undefined;
  const entries = scopeEntries({ cond, task, model }).filter((entry) => entry.counted);
  if (!entries.length) return null;
  const passes = entries.filter((entry) => entry.verdict === "pass");
  const cell = { trials: entries.length, passes: passes.length, not_graded: entries.filter((entry) => entry.verdict === "not graded").length };
  if (cond === "after_feedback") { cell.passed_first = passes.filter((entry) => entry.via === "first").length; cell.passed_after_feedback = passes.length - cell.passed_first; }
  return cell;
}

function renderMultiples() {
  const score = card.scorecard;
  const host = clear($("multiples"));
  const tasks = [...score.scored_tasks, score.harder_task];
  for (const entry of lookup.modelOrder.map((model) => score.models.find((item) => item.model === model)).filter(Boolean)) {
    const rows = tasks.map((task) => {
      const harder = task === score.harder_task;
      const cells = MULTI_CONDS.map(([cond, label, field]) => {
        const block = entry[field];
        let cell = block && (cond !== "after_feedback" || entry.replayed) ? block.by_task?.[task] : null;
        if (harder && cond !== "test_first" && (cond !== "after_feedback" || entry.replayed)) cell = harderCell(cond, entry.model, task);
        if (cell === undefined) return h("td", {}, h("span", { class: "mcell mcell-wait" }, h("span", { class: "frac" }, "…")));
        if (!cell || !cell.trials) return h("td", {}, h("span", { class: "mcell-none", title: cond === "after_feedback" ? "No second prints were run" : "Not run" }, "not run"));
        const said = `${entry.short}, ${taskLabel(task)}, ${label.toLowerCase()}: ${cell.passes} of ${cell.trials} pass` +
          (cond === "after_feedback" ? ` (${cell.passed_first} first time, ${cell.passed_after_feedback} after feedback)` : "") +
          (cell.not_graded ? `, ${cell.not_graded} not graded` : "");
        return h("td", {}, cellLink(said, { cond, task, model: entry.model }, { trials: cell.trials, passes: cell.passes }, { class: "mcell", "aria-label": `${said}. Open these ${cell.trials} trials.` }, [
          bar(cell, { split: cond === "after_feedback" }), h("span", { class: "frac" }, h("b", {}, String(cell.passes)), `/${cell.trials}`),
        ]));
      });
      return h("tr", { class: harder ? "multi-harder" : "" }, h("th", { scope: "row" }, taskShort(task), harder ? h("small", {}, "not in the totals") : null), cells);
    });
    host.append(h("article", { class: "multi" },
      h("h3", {}, modelLink(entry, "by-part panels")),
      h("table", {},
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Part")), MULTI_CONDS.map(([, label]) => h("th", { scope: "col" }, label)))),
        h("tbody", {}, rows))));
  }
  host.removeAttribute("aria-busy");
  $("by-task-fold").querySelector("summary").textContent = `The ${plural(host.children.length, "model")}, part by part`;
}

// ---- header and footer ----

function renderFoot() {
  const repo = index.transcript_base.replace(/\/blob\/.*$/, "");
  $("repo-link").href = repo;
  add(clear($("foot")),
    h("p", {}, `${index.trials.length.toLocaleString("en-US")} saved entries`,
      index.commit ? [" from commit ", h("a", { href: `${repo}/commit/${index.commit}` }, h("code", {}, index.commit.slice(0, 7)))] : null,
      ". The scorecard's numbers are computed by the repository's own scorecard script from the saved runs, the same numbers as its README."),
    h("p", {}, h("a", { href: repo + "#readme" }, "The README"), " explains the parts, the test prints behind the checks and what couldn't be graded; ",
      h("a", { href: repo + "/blob/main/docs/reference.md" }, "the reference"), " has the detail, including the assumptions the verdicts rest on. To run the eval yourself, see ",
      h("a", { href: repo + "#run-it" }, "Run it"), " in the README."));
}

// ---- filters ----

function chip(key, label, count, pressed, patch, extra = "") {
  return h("button", { type: "button", class: `chip ${extra}`, "aria-pressed": String(pressed), "data-k": key, onclick: () => navigate(patch) },
    label, count === null ? null : h("span", { class: "chip-n" }, String(count)));
}

function renderFilters() {
  const form = $("filters") || h("form", { id: "filters", class: "filters", onsubmit: (event) => event.preventDefault() });
  const focused = document.activeElement?.closest?.("#filters") ? document.activeElement.dataset.k : null;
  const groupEntries = lookup.entries.get(state.cond);
  const counted = (entry) => countable(entry);

  // condition
  const seg = h("div", { class: "seg" }, ["first", "after_feedback", "test_first"].map((key) => h("button", {
    type: "button", class: "seg-btn", "aria-pressed": String(key === state.cond), "data-k": "cond:" + key,
    onclick: () => navigate({ cond: key, verdict: "", reason: "", show: "" }),
  }, COND[key].short)));
  const others = index.groups.filter((group) => !["first", "test_first"].includes(group.key));
  const option = (group, label = group.label) => h("option", { value: group.key, selected: group.key === state.cond }, `${label} (${group.trials})`);
  const otherSelect = h("select", { id: "f-other", "data-k": "other", class: ["first", "after_feedback", "test_first"].includes(state.cond) ? "" : "is-set" },
    h("option", { value: "" }, "More runs…"),
    h("optgroup", { label: "Second prints" }, others.filter((group) => group.key === "second").map((group) => option(group, "Second prints on their own"))),
    Object.entries(CATEGORY_LABEL).map(([category, label]) => h("optgroup", { label }, others.filter((group) => group.category === category).map((group) => option(group)))));
  otherSelect.addEventListener("change", () => navigate({ cond: otherSelect.value || DEFAULTS.cond, verdict: "", reason: "", task: "all", show: "" }));

  // part
  const tasks = TASK_ORDER.filter((task) => groupEntries.some((entry) => entry.row.task === task));
  const taskEntries = groupEntries.filter((entry) => counted(entry) && modelMatches(entry.row, state.model));
  const taskChips = [];
  if (tasks.length > 1) taskChips.push(chip("task:all", "All parts", taskEntries.length, state.task === "all", { task: "all", reason: "" }));
  const scored = taskEntries.filter((entry) => taskMatches(entry.row, "scored"));
  if (scored.length && scored.length < taskEntries.length) {
    taskChips.push(chip("task:scored", "The four scored parts", scored.length, state.task === "scored", { task: "scored", reason: "" }));
  }
  for (const task of tasks) {
    taskChips.push(chip("task:" + task, taskLabel(task), taskEntries.filter((entry) => entry.row.task === task).length, state.task === task || tasks.length === 1, { task, reason: "" }));
  }

  // verdict
  const scope = scopeEntries(state);
  const verdictCounts = countVerdicts(scope.filter(counted));
  const verdictChips = [chip("verdict:", isHeadline() ? "All counted" : "All", scope.filter(counted).length, !state.verdict, { verdict: "", reason: "" })];
  for (const verdict of VERDICTS) {
    const slug = VERDICT[verdict].slug;
    if (!verdictCounts[verdict] && state.verdict !== slug) continue;
    const button = chip("verdict:" + slug, null, verdictCounts[verdict] || 0, state.verdict === slug, { verdict: state.verdict === slug ? "" : slug, reason: "" }, `chip-verdict ${VERDICT[verdict].cls}`);
    button.prepend(icon(VERDICT[verdict].icon), VERDICT[verdict].label);
    button.title = index.definitions[verdict];
    verdictChips.push(button);
  }
  const excluded = scope.filter((entry) => !entry.counted).length;
  if (isHeadline() && (excluded || state.verdict === "not-counted")) {
    const button = chip("verdict:not-counted", "Not counted", excluded, state.verdict === "not-counted", { verdict: state.verdict === "not-counted" ? "" : "not-counted", reason: "" }, "chip-excluded");
    button.title = index.definitions["not counted"];
    verdictChips.push(button);
  }
  if (VERDICT_SETS[state.verdict]) {
    const set = VERDICT_SETS[state.verdict];
    const button = chip("verdict:" + state.verdict, set.label, scope.filter((entry) => set.match(entry, state.cond)).length, true, { verdict: "", reason: "" });
    button.title = set.title;
    verdictChips.push(button);
  }
  const meanings = h("details", { class: "meanings" }, h("summary", {}, "What these mean"),
    h("dl", {}, [...VERDICTS, "not counted"].map((name) => h("div", {}, h("dt", {}, VERDICT[name] ? badge(name, { small: true }) : h("span", { class: "tag tag-excluded" }, "Not counted")), h("dd", {}, index.definitions[name])))));

  // model and reason
  const models = lookup.modelOrder.filter((model) => groupEntries.some((entry) => entry.row.model === model && taskMatches(entry.row, state.task)));
  const pooledHere = pooledModels().some((model) => models.includes(model)) && models.some((model) => !pooledModels().includes(model));
  // Each set of models is offered where it narrows this list, and always while it is the one chosen, so the menu
  // never reads "All models" over a filtered list. The sent-back set narrows a list of only the headline models too.
  const fedHere = fedModels().some((model) => models.includes(model)) && models.some((model) => !fedModels().includes(model));
  const modelSelect = h("select", { id: "f-model", "data-k": "model", class: state.model ? "is-set" : "" },
    h("option", { value: "" }, "All models"),
    pooledHere || state.model === POOLED ? h("option", { value: POOLED, selected: state.model === POOLED }, `The ${pooledModels().length} models run all three ways`) : null,
    fedHere || state.model === FED ? h("option", { value: FED, selected: state.model === FED }, `The ${fedModels().length} headline models whose failed prints were sent back`) : null,
    models.map((model) => h("option", { value: model, selected: model === state.model }, modelShort(model))));
  modelSelect.addEventListener("change", () => navigate({ model: modelSelect.value, reason: "" }));

  const reasons = reasonCounts(scope.filter((entry) => verdictMatches(entry, state)));
  const reasonSelect = h("select", { id: "f-reason", "data-k": "reason", class: state.reason ? "is-set" : "", disabled: !reasons.length && !state.reason },
    h("option", { value: "" }, reasons.length ? "Any reason" : "No reasons in this list"));
  for (const kind of ["failed", "not graded", "declined", "no design", "error"]) {
    const ofKind = reasons.filter((reason) => reason.kind === kind);
    if (!ofKind.length) continue;
    reasonSelect.append(h("optgroup", { label: kind === "failed" ? "Failed because" : kind === "not graded" ? "Not graded because" : VERDICT[ISSUE_VERDICT[kind]].label },
      ofKind.map((reason) => h("option", { value: reason.key, selected: reason.key === state.reason }, `${reason.text} (${reason.count})`))));
  }
  if (state.reason && !reasons.some((reason) => reason.key === state.reason)) reasonSelect.append(h("option", { value: state.reason, selected: true }, `${index.reason_groups[state.reason]} (0)`));
  reasonSelect.addEventListener("change", () => navigate({ reason: reasonSelect.value }));

  const dirty = state.task !== "all" || state.verdict || state.model || state.reason;
  add(clear(form),
    h("div", { class: "f-row f-cond" }, h("span", { class: "f-label", id: "fl-cond" }, "Condition"),
      h("div", { class: "f-controls", role: "group", "aria-labelledby": "fl-cond" }, seg,
        h("label", { class: "sr-only", for: "f-other" }, "More runs: second prints, controls, pilots and replay studies"), otherSelect)),
    h("div", { class: "f-row" }, h("span", { class: "f-label", id: "fl-task" }, "Part"),
      h("div", { class: "f-controls chips", role: "group", "aria-labelledby": "fl-task" }, taskChips)),
    h("div", { class: "f-row" }, h("span", { class: "f-label", id: "fl-verdict" }, "Verdict"),
      h("div", { class: "f-controls chips", role: "group", "aria-labelledby": "fl-verdict" }, verdictChips, meanings)),
    h("div", { class: "f-row f-narrow" }, h("span", { class: "f-label", id: "fl-narrow" }, "Narrow to"),
      h("div", { class: "f-controls", role: "group", "aria-labelledby": "fl-narrow" },
        h("label", { class: "sr-only", for: "f-model" }, "Model"), modelSelect,
        h("label", { class: "sr-only", for: "f-reason" }, "Reason a design failed or wasn't graded"), reasonSelect,
        dirty ? h("button", { type: "button", class: "btn btn-quiet", "data-k": "clear", onclick: () => navigate({ task: "all", verdict: "", model: "", reason: "", show: "" }) }, "Clear filters") : null)));
  if (!form.isConnected) $("filter-host").append(form);
  if (focused) form.querySelector(`[data-k="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
}

function renderScopeNote() {
  const group = lookup.groups.get(state.cond);
  const note = h("div", { class: "scope-note" + (isHeadline() ? "" : " scope-other") },
    h("p", {}, h("strong", {}, group.label + ". "), group.description,
      isHeadline() ? null : [" ", h("span", { class: "tag tag-excluded" }, "Not in the scorecard")]));
  if (state.cond === "second") note.append(h("p", {}, "The scorecard's after-feedback column counts these together with the first prints that passed; ", stateLink({ cond: "after_feedback", verdict: "", reason: "" }, {}, "see them counted that way"), "."));
  if (state.verdict === "not-counted") note.append(h("p", {}, index.definitions["not counted"]));
  add(clear($("scope-note")), note);
  add(clear($("notice")), notices.length ? h("p", { class: "notice" }, `This link asked for something that isn't here, so it was left out: ${notices.join(", ")}.`) : null);
}

// "Showing 2 of 110 first prints: Tripod plate, not graded"
function summaryText() {
  const total = scopeEntries(state).filter((entry) => countable(entry)).length;
  const noun = COND[state.cond]?.noun || `entries in “${lookup.groups.get(state.cond).label}”`;
  const narrowed = [];
  if (state.task === "scored") narrowed.push("the four scored parts");
  else if (state.task !== "all") narrowed.push(taskLabel(state.task));
  if (state.model) narrowed.push(modelSet(state.model) ? modelSetLabel(state.model) : modelShort(state.model));
  const picked = [];
  if (state.verdict) picked.push(state.verdict === "not-counted" ? "not counted" : (VERDICT_SETS[state.verdict] || VERDICT[verdictFromSlug(state.verdict)]).label.toLowerCase());
  if (state.reason) picked.push(`reason: ${index.reason_groups[state.reason]}`);
  const scope = `${total.toLocaleString("en-US")} ${noun}${narrowed.length ? ` (${narrowed.join(", ")})` : ""}`;
  if (state.verdict === "not-counted") return `Showing ${shown.length} not counted, beside the ${scope}`;
  return picked.length ? `Showing ${shown.length.toLocaleString("en-US")} of ${scope}: ${picked.join("; ")}` : `Showing all ${scope}`;
}

// With a reason chosen (a shared ?reason= link, say), what that failure looks like comes before its designs: the same
// picture, labelled the same way, as in "Why first prints don't pass".
function reasonHeader() {
  if (!state.reason) return null;
  const picture = index.reason_pictures?.[state.reason];
  const verdict = ISSUE_VERDICT[lookup.reasonKind.get(state.reason)] || "error";
  let figure = null;
  if (picture) {
    const image = h("img", { src: picture.thumb, alt: "", decoding: "async", width: String(picture.width || 96), height: String(picture.height || 72) });
    figure = h("a", { class: `reason-pic${picture.kind === "drawing" ? " reason-pic-drawing" : ""}`, href: picture.url, "aria-label": "The picture, full size" }, image);
    image.addEventListener("error", () => figure.remove(), { once: true });
  }
  return h("div", { class: `reason-head ${VERDICT[verdict].cls}` }, figure,
    h("div", { class: "reason-words" },
      h("p", { class: "reason-kicker" }, badge(verdict, { small: true }), ` ${plural(shown.length, "design")} in this list, for one reason`),
      h("h3", {}, index.reason_groups[state.reason] || state.reason),
      // a drawing's caption already says whose it is and that it wasn't printed; a photo's gets the list's label first
      picture ? h("p", { class: "reason-cap" }, picture.kind === "drawing" ? [h("b", {}, "Picture: "), picture.caption.replace(/^The /, "the ")]
        : [h("b", {}, pictureKind(picture) + ". "), picture.caption]) : null,
      h("p", {}, h("button", { type: "button", class: "btn btn-small", "data-k": "reason-clear", onclick: () => { navigate({ reason: "" }); refocus(".reasons > summary"); } }, "Show every reason"))));
}

function renderReasons() {
  const host = clear($("reasons"));
  add(host, reasonHeader());
  const reasons = reasonCounts(scopeEntries(state).filter((entry) => verdictMatches(entry, state)));
  if (!reasons.length) return;
  const open = !state.reason && ["fail", "not-graded"].includes(state.verdict);  // a chosen reason: go straight to its designs
  const settle = new Map(Object.values(index.not_graded_reasons).map((item) => [item.reason_group, item.settle]));
  const list = h("ul", { class: "reason-list" });
  for (const reason of reasons) {
    const pressed = state.reason === reason.key;
    list.append(h("li", {}, h("button", { type: "button", class: "reason", "aria-pressed": String(pressed), onclick: () => { navigate({ reason: pressed ? "" : reason.key }); refocus(pressed ? ".reasons > summary" : '[data-k="reason-clear"]'); } },
      badge(ISSUE_VERDICT[reason.kind] || "error", { small: true }),
      h("span", { class: "reason-text" }, h("span", {}, reason.text), settle.get(reason.key) ? h("small", {}, "The print that would settle it: ", settle.get(reason.key)) : null),
      h("span", { class: "reason-n" }, String(reason.count)))));
  }
  host.append(h("details", { class: "reasons", open: Boolean(open) },
    h("summary", {}, h("span", {}, `Why: ${plural(reasons.length, "reason")} in this list`), h("small", {}, "designs per reason; a design with two reasons counts under both")),
    list));
}

// ---- results ----

function entryFlag(entry) {
  const row = entry.row;
  if (isHeadline() && !entry.counted) return h("span", { class: "flag" }, "not counted");
  if (state.cond === "after_feedback") {
    return h("span", { class: "flag" }, entry.via === "second" ? "second print" : entry.verdict === "pass" ? "first time" : "not replayed");
  }
  if (row.condition_key === "can_test" && row.kind === "trial" && row.verdict !== "error") {
    return h("span", { class: "flag" + (row.test_print_rounds_asked ? "" : " flag-zero") }, row.test_print_rounds_asked ? `asked for test prints ×${row.test_print_rounds_asked}` : "asked for no test prints");
  }
  return null;
}

const SHORT_NONE = [[/code didn't run/i, "Code didn't run"], [/infrastructure/i, "Stopped: infrastructure error"], [/No design was handed in/i, "No design handed in"], [/had no parts/i, "No parts handed in"]];

function thumbBox(row) {
  if (!row.thumb) {
    const why = row.thumb_none_reason || "No render of this design is saved";
    return h("span", { class: "thumb" }, h("span", { class: "thumb-none", title: why }, (SHORT_NONE.find(([test]) => test.test(why)) || [0, "No picture"])[1]));
  }
  const image = h("img", { src: row.thumb, alt: "", loading: "lazy", decoding: "async", width: "640", height: "512" });
  const box = h("span", { class: "thumb" + (row.thumb_role === "test print" ? " thumb-test" : "") }, image, row.thumb_role === "test print" ? h("span", { class: "thumb-tag" }, "test print only") : null);
  image.addEventListener("error", () => box.replaceChildren(h("span", { class: "thumb-none" }, "Picture didn't load")), { once: true });
  return box;
}

function entryLabel(entry) {
  const row = entry.row;
  const reason = row.issues[0] ? `. ${readerReason(row.issues[0].reason)}` : "";
  const how = state.cond === "after_feedback" ? (entry.via === "second" ? ", second print" : ", first print") : "";
  return `${row.model_short}, ${taskLabel(row.task)}, trial ${row.trial}${how}: ${VERDICT[entry.verdict].label}${reason}` + (isHeadline() && !entry.counted ? `. Not counted: ${row.excluded_reason}` : "");
}

function trialCard(entry) {
  const row = entry.row;
  return openTrialOnClick(h("a", { class: `card ${VERDICT[entry.verdict].cls}`, href: hrefFor({ trial: row.slug }), "data-slug": row.slug, "aria-label": entryLabel(entry) },
    thumbBox(row),
    h("span", { class: "card-body" }, badge(entry.verdict, { small: true }), h("span", { class: "card-trial" }, `Trial ${row.trial}`), entryFlag(entry))), row.slug);
}

const rowKey = (task, model) => `${task}|${model}`;

// Everything a model's row says once, so the cards don't have to repeat it.
function rowSummary(task, model, entries) {
  const all = scopeEntries({ cond: state.cond, task, model }).filter((entry) => countable(entry));
  const passes = all.filter((entry) => entry.verdict === "pass");
  const cell = { passes: passes.length, trials: all.length, not_graded: all.filter((entry) => entry.verdict === "not graded").length };
  const lines = [];
  if (state.verdict === "not-counted") {
    const why = new Map();
    for (const entry of entries) why.set(entry.row.excluded_reason, (why.get(entry.row.excluded_reason) || 0) + 1);
    for (const [reason, count] of why) lines.push(h("p", { class: "row-line" }, `${count} not counted: ${reason}`));
    return { stat: `${entries.length} not counted`, cell: null, lines };
  }
  let stat = `${cell.passes} of ${cell.trials} pass`;
  if (state.cond === "after_feedback") {
    const first = passes.filter((entry) => entry.via === "first").length;
    cell.passed_first = first; cell.passed_after_feedback = passes.length - first;
    if (all.some((entry) => entry.replayed)) stat += `: ${first} first time, ${passes.length - first} after feedback`;
    else lines.push(h("p", { class: "row-line" }, "No second prints were run for this model."));
  }
  if (entries.length !== all.length) stat += ` · ${entries.length} shown`;
  const reasons = reasonCounts(entries);
  if (reasons.length) {
    lines.push(h("ul", { class: "row-reasons", "aria-label": "Reasons in this row. Each one filters the list." }, reasons.slice(0, 3).map((reason) => {
      const pressed = state.reason === reason.key;
      return h("li", {}, h("button", {
        type: "button", class: "row-reason", "aria-pressed": String(pressed), "data-reason": reason.key,
        title: pressed ? "Showing only the designs with this reason. Press to show every reason again." : "Show only the designs with this reason",
        onclick: () => navigateInPlace({ reason: pressed ? "" : reason.key }, rowKey(task, model), `[data-reason="${CSS.escape(reason.key)}"]`),
      }, icon(pressed ? "close" : "filter"), h("span", {}, h("b", {}, `${reason.count} ×`), " ", reason.text)));
    }), reasons.length > 3 ? h("li", { class: "row-more" }, `and ${plural(reasons.length - 3, "other reason")}`) : null));
  }
  const drawn = entries.find((entry) => entry.verdict === "fail" && entry.row.views > 0);
  if (drawn) {
    lines.push(h("p", { class: "row-line" }, openTrialOnClick(h("a", { class: "row-see", href: hrefFor({ trial: drawn.row.slug }) }, `See where trial ${drawn.row.trial} fails`), drawn.row.slug)));
  }
  const tested = entries.filter((entry) => entry.row.condition_key === "can_test" && entry.row.kind === "trial" && entry.verdict !== "error");
  if (tested.length) {
    const asked = tested.filter((entry) => entry.row.test_print_rounds_asked > 0).length;
    const told = tested.filter((entry) => entry.row.cant_tell).length;
    lines.push(h("p", { class: "row-line" }, `Asked for test prints in ${asked} of ${tested.length}`, told ? `; the person couldn't tell in ${told}` : "", "."));
  }
  return { stat, cell, lines };
}

function modelRow(task, model, entries, showTask) {
  const summary = rowSummary(task, model, entries);
  return h("section", { class: "model-row", "data-row": rowKey(task, model), "aria-label": `${modelShort(model)}, ${taskLabel(task)}` },
    h("div", { class: "model-head" },
      h("h4", {}, modelShort(model), showTask ? h("small", {}, taskLabel(task)) : null),
      h("p", { class: "model-stat" }, summary.stat),
      summary.cell ? bar(summary.cell, { split: state.cond === "after_feedback" }) : null,
      summary.lines),
    h("div", { class: "cards" }, entries.map(trialCard)));
}

// A trial's link opens it over the list.
function openTrialOnClick(link, slug) {
  link.addEventListener("click", (event) => {
    if (!plainClick(event)) return;
    event.preventDefault();
    navigate({ trial: slug }, { opened: true });
  });
  return link;
}

// One line per model: its name opens that model's row of pictures, and each mark is one trial and opens it.
function stripRow(task, model, entries) {
  const summary = rowSummary(task, model, entries);
  const top = reasonCounts(entries)[0];
  const patch = { task, model, show: "" };
  listCheck.links += 1 + entries.length;
  const opens = selectEntries({ ...state, ...patch }).length;
  if (opens !== entries.length) listCheck.problems.push(`strip ${modelShort(model)}, ${taskLabel(task)}: ${entries.length} marks, but its link opens ${opens} designs`);
  const name = stateLink(patch, { class: "strip-model", "aria-label": `${modelShort(model)}, ${taskLabel(task)}: ${verdictLine(countVerdicts(entries))}. Open these ${entries.length} designs as pictures.` },
    [modelShort(model), icon("next", "icon strip-go")]);
  const marks = h("ul", { class: "marks", "aria-label": `${modelShort(model)}, ${taskLabel(task)}: ${plural(entries.length, "design")}, one mark each` }, entries.map((entry) => {
    const said = entryLabel(entry);
    if (!lookup.bySlug.has(entry.row.slug)) listCheck.problems.push(`strip mark with no trial: ${entry.row.slug}`);
    return h("li", {}, openTrialOnClick(h("a", { class: `mark ${VERDICT[entry.verdict].cls}`, href: hrefFor({ trial: entry.row.slug }), "data-slug": entry.row.slug, "aria-label": said, title: said },
      icon(VERDICT[entry.verdict].icon)), entry.row.slug));
  }));
  return h("div", { class: "strip", "data-row": rowKey(task, model) },
    name,
    h("span", { class: "strip-stat" }, summary.stat),
    marks,
    h("span", { class: "strip-reason" }, top ? [h("b", {}, `${top.count} ×`), " ", top.text] : ""));
}

function taskHead(task, entries) {
  const info = index.tasks[task];
  const provided = state.cond === "after_feedback" ? countVerdicts(scopeEntries({ cond: state.cond, task, model: "" })) : index.counts[isHeadline() ? "counted" : "all"][state.cond]?.[task] || {};
  const line = state.verdict === "not-counted"
    ? `${entries.length} not counted, each with its reason`
    : state.model
      ? `${modelSet(state.model) ? "These models" : modelShort(state.model)}: ${verdictLine(countVerdicts(scopeEntries({ cond: state.cond, task, model: state.model }).filter((entry) => countable(entry))))}`
      : `${isHeadline() ? "Counted" : "All"}: ${verdictLine(provided)}`;
  return h("div", { class: "task-head" },
    h("h3", {}, info.label),
    h("p", { class: "task-counts" }, line),
    h("details", { class: "request", open: Boolean(index.tasks[state.task]) && matchMedia("(min-width: 760px)").matches },
      h("summary", {}, "What the person asked for"),
      h("blockquote", {}, info.request)));
}

function renderResults() {
  const entries = sortEntries(selectEntries(state));
  shown = entries;
  const host = clear($("results"));
  sentinelWatch?.disconnect();
  pending = [];
  listCheck = { links: 0, problems: [] };
  const strips = state.show === "strips" || (state.show !== "pictures" && entries.length > STRIPS_ABOVE);
  $("result-count").textContent = summaryText();
  const tools = clear($("result-tools"));
  if (entries.length > 12) {
    tools.append(h("button", { type: "button", class: "btn btn-small", id: "view-toggle", onclick: () => { navigate({ show: strips ? "pictures" : "strips" }, { replace: true }); refocus("#view-toggle"); } },
      strips ? `Show all ${entries.length} as pictures` : "Show one line per model"));
  }
  if (!entries.length) { host.append(emptyState()); return; }

  const byTask = new Map();
  let last = null;
  for (const entry of entries) {
    const { task, model } = entry.row;
    if (!last || last.task !== task || last.model !== model) {
      last = { task, model, entries: [], firstOfTask: !last || last.task !== task };
      pending.push(last);
    }
    last.entries.push(entry);
    byTask.set(task, (byTask.get(task) || []).concat(entry));
  }
  const manyTasks = byTask.size > 1;
  if (strips) host.classList.add("as-strips"); else host.classList.remove("as-strips");
  const place = (group, before) => {
    if (group.firstOfTask) host.insertBefore(taskHead(group.task, byTask.get(group.task)), before);
    host.insertBefore(strips ? stripRow(group.task, group.model, group.entries) : modelRow(group.task, group.model, group.entries, manyTasks), before);
  };
  if (strips) { for (const group of pending.splice(0)) place(group, null); return; }

  const sentinel = h("div", { class: "sentinel", "aria-hidden": "true" });
  host.append(sentinel);
  const renderBatch = () => {
    for (const group of pending.splice(0, ROWS_PER_BATCH)) place(group, sentinel);
    if (!pending.length) { sentinelWatch?.disconnect(); sentinel.remove(); }
  };
  renderBatch.place = place;
  renderResults.batch = renderBatch;
  renderBatch();
  if (pending.length) {
    // An observer only reports changes, so after a batch the sentinel is observed afresh: if it is still near the
    // screen, that reports again and the next batch follows.
    sentinelWatch = new IntersectionObserver((seen) => {
      if (!seen.some((entry) => entry.isIntersecting)) return;
      renderBatch();
      sentinelWatch.unobserve(sentinel);
      if (pending.length) sentinelWatch.observe(sentinel);
    }, { rootMargin: "900px 0px" });
    sentinelWatch.observe(sentinel);
  }
}

const findCard = (slug) => document.querySelector(`#results [data-slug="${CSS.escape(slug)}"]`);  // a card, or a mark in a strip

// Put rows in the page until a given trial's card is there (to focus it after its dialog closes).
function renderUntil(slug) {
  let guard = 0;
  while (pending.length && !findCard(slug) && guard++ < 200) renderResults.batch();
}

function emptyState() {
  const excluded = scopeEntries(state).filter((entry) => !entry.counted).length;
  const box = h("div", { class: "empty" }, h("p", {}, h("strong", {}, "No trials match these filters.")));
  if (isHeadline() && excluded && state.verdict !== "not-counted") {
    box.append(h("p", {}, `${plural(excluded, "entry", "entries")} here ${excluded === 1 ? "isn't" : "aren't"} counted (for example runs that stopped on an infrastructure error). `,
      stateLink({ verdict: "not-counted", reason: "" }, {}, "Show the entries not counted"), "."));
  }
  box.append(h("p", {}, h("button", { type: "button", class: "btn", onclick: () => { navigate({ task: "all", verdict: "", model: "", reason: "" }); refocus("#results-top"); } }, "Clear the filters")));
  return box;
}

// ---- the dock: a one-line summary and the filters, once the filter panel has scrolled away ----

function setUpDock() {
  const sheet = $("filter-sheet");
  const dock = $("dock");
  $("dock-filters").addEventListener("click", () => { $("sheet-body").append($("filters")); sheet.showModal(); });
  $("sheet-close").addEventListener("click", () => sheet.close());
  sheet.addEventListener("click", (event) => { if (event.target === sheet) sheet.close(); });
  sheet.addEventListener("close", () => { $("filter-host").append($("filters")); $("dock-filters").focus({ preventScroll: true }); update(); });
  function update() {
    const host = $("filter-host").getBoundingClientRect();
    const section = $("trials").getBoundingClientRect();
    dock.hidden = !(host.bottom < 0 && section.bottom > innerHeight * 0.4) || sheet.open;
  }
  addEventListener("scroll", update, { passive: true });
  addEventListener("resize", update);
  update();
}

// ---- one trial, in a dialog ----

function trialContext(slug) {
  const at = shown.findIndex((entry) => entry.row.slug === slug);
  const step = (offset) => (at < 0 ? null : shown[at + offset]?.row || null);
  return {
    meta: meta(), ready: Boolean(index), fetchDetail, hrefFor, listHref,
    position: at < 0 ? null : { at: at + 1, of: shown.length },
    prev: step(-1), next: step(1),
    groupLabel: (key) => lookup.groups.get(key)?.label || "",
    open: (target) => navigate({ trial: target }, { replace: true }),
    openOther: (target) => navigate({ trial: target }),  // a linked trial (its second print): Back returns to this one
    close: closeTrial,
    rowOf: (id) => lookup.byId.get(id) || lookup.bySlug.get(id) || null,
    listLink: (patch, attrs, kids) => stateLink({ ...patch, trial: "" }, attrs, kids, { fromDefaults: true, toResults: true }),
  };
}

function closeTrial() {
  if (!index) { location.href = location.pathname; return; }
  if (history.state?.trialOpened) history.back();
  else navigate({ trial: "" }, { replace: true });
}

function showDialog(slug, row) {
  const dialog = $("trial-dialog");
  const body = $("trial-body");
  renderDetailShell(body, row, trialContext(slug));
  if (!dialog.open) dialog.showModal();
  document.documentElement.classList.add("modal-open");
  dialog.scrollTop = 0;
  body.querySelector("#trial-title")?.focus({ preventScroll: true });
}

async function fillDialog(slug, row) {
  const body = $("trial-body");
  try {
    const detail = await fetchDetail(slug);
    if (dialogSlug === slug) renderDetail(body, row || detail, detail, trialContext(slug));
  } catch (error) {
    if (dialogSlug !== slug) return;
    body.querySelector(".td-loading")?.replaceWith(h("div", { class: "empty", role: "alert" },
      h("p", {}, h("strong", {}, "This trial's detail didn't load. "), String(error.message || error)),
      h("p", {}, h("button", { type: "button", class: "btn", onclick: () => { dialogSlug = null; syncDialog(); } }, "Try again"))));
  }
}

function syncDialog() {
  const dialog = $("trial-dialog");
  if (!state.trial) {
    if (dialog.open) { closingFromCode = true; dialog.close(); closingFromCode = false; }
    teardown();
    document.documentElement.classList.remove("modal-open");
    if (dialogSlug) {
      const slug = dialogSlug;
      dialogSlug = null;
      renderUntil(slug);
      const target = findCard(slug) || $("results-top");
      // Back to the list the trial came from, not the top of the page.
      if (target.getBoundingClientRect().top < 60 || target.getBoundingClientRect().bottom > innerHeight) target.scrollIntoView({ block: "center" });
      target.focus({ preventScroll: true });
    }
    return;
  }
  const slug = state.trial;
  if (dialogSlug === slug && dialog.open) { updateShell($("trial-body"), lookup.bySlug.get(slug), trialContext(slug)); return; }
  dialogSlug = slug;
  showDialog(slug, lookup.bySlug.get(slug));
  fillDialog(slug, lookup.bySlug.get(slug));
}

function setUpDialog() {
  const dialog = $("trial-dialog");
  dialog.addEventListener("close", () => { if (!closingFromCode && state.trial) closeTrial(); });
  dialog.addEventListener("click", (event) => { if (event.target === dialog) closeTrial(); });
  dialog.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey || !index) return;
    if (event.target.closest("input, select, textarea, canvas, pre, summary, [contenteditable]")) return;
    const context = trialContext(state.trial);
    if (event.key === "ArrowLeft" && context.prev) { event.preventDefault(); context.open(context.prev.slug); }
    if (event.key === "ArrowRight" && context.next) { event.preventDefault(); context.open(context.next.slug); }
  });
}

// A ?trial= link: show that trial from its own file while the index is still on its way.
async function openEarly(slug) {
  if (!/^[A-Za-z0-9._-]+$/.test(slug)) return;
  try {
    const detail = await fetchDetail(slug);
    if (index || dialogSlug) return;
    earlyDetail = detail;
    dialogSlug = slug;
    showDialog(slug, detail);
    renderDetail($("trial-body"), detail, detail, trialContext(slug));
    performance.mark("trial-painted");
  } catch { /* the index will say whether the trial exists */ }
}

// ---- checks that the page's own counting agrees with the data's aggregates (see the console) ----

function verifyCounts() {
  const problems = [];
  let compared = 0;
  const same = (label, mine, theirs) => { compared += 1; if (mine !== theirs) problems.push(`${label}: page counts ${mine}, data says ${theirs}`); };
  const rows = index.trials;
  for (const group of index.groups) same(`group ${group.key} entries`, rows.filter((row) => row.group === group.key).length, group.trials);
  for (const [which, keep] of [["counted", (row) => row.counted], ["all", () => true]]) {
    for (const [group, tasks] of Object.entries(index.counts[which])) {
      for (const [task, verdicts] of Object.entries(tasks)) {
        for (const verdict of VERDICTS) {
          same(`counts.${which} ${group} ${task} ${verdict}`, rows.filter((row) => keep(row) && row.group === group && row.task === task && row.verdict === verdict).length, verdicts[verdict] || 0);
        }
      }
    }
  }
  // Every scorecard cell and by-part cell, counted by the page's own filtering.
  for (const entry of index.scorecard.models) {
    const count = (cond, task, label, cell) => {
      const list = selectEntries({ ...DEFAULTS, cond, task, model: entry.model });
      same(`${entry.short} ${label} trials`, list.length, cell.trials);
      same(`${entry.short} ${label} passes`, list.filter((item) => item.verdict === "pass").length, cell.passes);
      if ("not_graded" in cell) same(`${entry.short} ${label} not graded`, list.filter((item) => item.verdict === "not graded").length, cell.not_graded);
      if ("passed_first" in cell) same(`${entry.short} ${label} passed first time`, list.filter((item) => item.verdict === "pass" && item.via === "first").length, cell.passed_first);
      if (cell.cant_tell) same(`${entry.short} ${label} can't tell`, list.filter((item) => item.row.cant_tell).length, cell.cant_tell.trials);
    };
    for (const [cond, block] of [["first", entry.first], ["after_feedback", entry.after_feedback], ["test_first", entry.test_first]]) {
      if (!block) continue;
      count(cond, "scored", `${cond} total`, block);
      for (const [task, cell] of Object.entries(block.by_task)) count(cond, task, `${cond} ${task}`, cell);
      if (block.excluded) same(`${entry.short} ${cond} excluded`, scopeEntries({ cond, task: "scored", model: entry.model }).filter((item) => !item.counted).length, block.excluded.count);
    }
  }
  verifyChart(same);
  // After feedback: the entry points at the print whose verdict the scorecard counts.
  for (const item of lookup.entries.get("after_feedback")) same(`after feedback verdict of ${item.first.id}`, item.row.verdict, item.verdict);
  // Every link drawn on the page (headline tiles, reasons chart, scorecard cells, by-part bars) opens a list with
  // exactly the numbers the link shows.
  let links = 0;
  for (const link of linkChecks.values()) {
    const list = selectEntries({ ...DEFAULTS, ...link.patch });
    links += 1;
    if ("atLeast" in link) { same(`link “${link.label}” opens at least ${link.atLeast}`, list.length >= link.atLeast, true); continue; }
    same(`link “${link.label}” trials`, list.length, link.trials);
    if ("passes" in link) same(`link “${link.label}” passes`, list.filter((item) => item.verdict === "pass").length, link.passes);
  }
  countProblems = problems;
  const result = { compared, links, problems: [...problems, ...listCheck.problems], list: listCheck, detail: detailCheck };
  if (problems.length) console.error(`Counts check: ${problems.length} of ${compared} comparisons disagree`, problems);
  else console.info(`Counts check: ${compared} comparisons between the page's filtering and the data's aggregates, all equal (${links} scorecard links each open a list with the cell's own numbers).`);
  window.resultsSiteCheck = result;
  return result;
}

// ---- start ----

function render() {
  renderFilters();
  renderScopeNote();
  renderResults();
  renderReasons();
  $("dock-summary").textContent = $("result-count").textContent;
  syncDialog();
  // the list's own links (each strip's name opens as many designs as it has marks), kept current with the list
  if (listCheck.problems.length) console.error("List check: a strip's link doesn't open the designs it shows", listCheck.problems);
  if (window.resultsSiteCheck) Object.assign(window.resultsSiteCheck, { list: listCheck, problems: [...countProblems, ...listCheck.problems] });
}

function fail(host, error) {
  add(clear(host), h("div", { class: "empty", role: "alert" },
    h("p", {}, h("strong", {}, "The results didn't load. "), String(error.message || error)),
    h("p", {}, h("button", { type: "button", class: "btn", onclick: () => location.reload() }, "Reload"))));
}

async function start() {
  const params = new URLSearchParams(location.search);
  const wanted = params.get("trial");
  const indexLoading = getJson("data/index.json");
  indexLoading.catch(() => {});
  if (wanted) openEarly(wanted);
  setUpDialog();
  try {
    useScorecard(await getJson("data/scorecard.json"));
    renderFinding();
    renderScorecard();
    renderMultiples();
    performance.mark("scorecard-painted");
  } catch (error) {
    console.warn("data/scorecard.json didn't load; waiting for the index", error);
  }
  try {
    useIndex(await indexLoading);
  } catch (error) {
    fail($("results"), error);
    $("result-count").textContent = "";
    return;
  }
  if (!$("scorecard-body").querySelector("table")) { renderFinding(); renderScorecard(); }
  renderMultiples();           // again, now that the Estoa box's first-print and after-feedback cells can be counted
  renderWhy();
  wireFailingExample();
  renderFoot();
  readUrl();
  if (earlyDetail && state.trial !== earlyDetail.slug) dialogSlug = null;
  render();
  setUpDock();
  addEventListener("popstate", () => { readUrl(); render(); });
  addEventListener("hashchange", openTargetedFold);
  phone.addEventListener("change", () => { if (!phone.matches) for (const fold of document.querySelectorAll(".phone-fold")) fold.open = true; });
  openTargetedFold();
  if (!state.trial && ["cond", "task", "verdict", "model", "reason"].some((key) => params.has(key))) scrollToResults(false);
  performance.mark("trials-painted");
  verifyCounts();
}

start();
