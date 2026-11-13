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
//   model   the model id after its slash, e.g. gemini-4-argon; or run-all-three-ways (the models in the headline)
//   reason  a reason group's key, e.g. holed-roof or a-tripod-head-recess-under-5-mm-deep
//   show    pictures | strips     overrides the automatic choice between picture cards and one line per model
//   trial   a trial's slug: opens that trial

import {
  h, add, clear, icon, badge, VERDICTS, VERDICT, ISSUE_VERDICT, verdictFromSlug, TASK_ORDER,
  taskSlug, taskFromSlug, condSlug, condFromSlug, modelSlug, slugify, pct, money2, hours1, grams, tokens, plural,
} from "./util.js";
import { renderDetail, renderDetailShell, updateShell, teardown } from "./detail.js";

const $ = (id) => document.getElementById(id);
const ROWS_PER_BATCH = 8;       // model rows put in the page at a time
const STRIPS_ABOVE = 150;       // more trials than this and each model gets one line, not a row of pictures
const POOLED = "pooled";        // the model filter's value for "the models run in all three ways"
const POOLED_SLUG = "run-all-three-ways";
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

export function fetchDetail(slug) {
  if (!details.has(slug)) {
    const promise = getJson(`data/trials/${encodeURIComponent(slug)}.json`);
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
const taskMatches = (row, task) => task === "all" || (task === "scored" ? meta().tasks[row.task].scored : row.task === task);
const modelMatches = (row, model) => !model || (model === POOLED ? pooledModels().includes(row.model) : row.model === model);
const condShort = (cond) => COND[cond]?.short || lookup.groups.get(cond)?.label || cond;

// ---- URL state ----

function readUrl() {
  const params = new URLSearchParams(location.search);
  const next = { ...DEFAULTS };
  notices = [];
  const unknown = (name, value) => notices.push(`${name} “${value}”`);
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
  if (verdict === "not-counted" || verdictFromSlug(verdict)) next.verdict = verdict;
  else if (verdict) unknown("verdict", verdict);
  const model = params.get("model");
  if (model === POOLED_SLUG) next.model = POOLED;
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
  if (next.model) params.set("model", next.model === POOLED ? POOLED_SLUG : modelSlug(next.model));
  if (next.reason) params.set("reason", next.reason);
  if (next.show) params.set("show", next.show);
  if (next.trial) params.set("trial", next.trial);
  const query = params.toString();
  return location.pathname + (query ? "?" + query : "");
}

// A link to a list, from anywhere: starts from the defaults, not from the filters now set.
const listHref = (patch) => hrefFor(patch, DEFAULTS);

function navigate(patch, { replace = false, toResults = false, fromDefaults = false, opened = false } = {}) {
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
  else if (!openingTrial && $("results-top").getBoundingClientRect().top < 0) scrollToResults(false);
}

// Keep the filters consistent with the chosen condition: a part or model with no entries there falls back to "all".
function normalise() {
  const inGroup = lookup.entries.get(state.cond) || [];
  if (state.task !== "all" && !inGroup.some((entry) => taskMatches(entry.row, state.task))) state.task = "all";
  if (state.task === "scored" && inGroup.every((entry) => taskMatches(entry.row, "scored"))) state.task = "all";
  if (state.model && !inGroup.some((entry) => modelMatches(entry.row, state.model))) state.model = "";
  if (state.verdict === "not-counted" && (!isHeadline() || !inGroup.some((entry) => !entry.counted))) state.verdict = "";
}

function scrollToResults(focus) {
  const target = $("results-top");
  target.scrollIntoView({ behavior: reducedMotion() || !focus ? "auto" : "smooth", block: "start" });
  if (focus) target.focus({ preventScroll: true });
}

const plainClick = (event) => !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0);

// A link that changes the list without loading the page again; modified clicks still open a new tab. Before the
// index has loaded the link works as an ordinary link.
function stateLink(patch, attrs, kids, options = {}) {
  const link = h("a", { href: options.fromDefaults ? listHref(patch) : hrefFor(patch), ...attrs }, kids);
  link.addEventListener("click", (event) => {
    if (!plainClick(event) || !index) return;
    event.preventDefault();
    navigate(patch, options);
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

function verdictMatches(entry, s) {
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

function renderFinding() {
  const score = card.scorecard;
  const pooled = score.pooled;
  const tell = score.cant_tell;
  const tile = (key, cond, label, note) => {
    const cell = pooled[key];
    return cellLink(`headline ${key}`, { cond, task: "scored", model: POOLED }, { trials: cell.trials, passes: cell.passes }, { class: "stat" }, [
      h("span", { class: "stat-rate" }, pct(cell.rate)),
      h("span", { class: "stat-label" }, label),
      h("span", { class: "stat-frac" }, `${cell.passes} of ${cell.trials}`),
      note ? h("span", { class: "stat-note" }, note) : null,
    ]);
  };
  const heading = $("finding");
  add(clear(heading),
    tile("first", "first", "on the first print", null),
    tile("after_feedback", "after_feedback", "after one round of feedback", "the same first prints; each one that didn't pass was sent back once"),
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
  const pick = firsts.find((row) => row.issues.length === 1 && row.issues[0].reason_group === "holed-roof" && row.task === "tripod-plate") || firsts[0];
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
  $("hero-cap").textContent = `One failing design (${pick.model_short}, ${taskLabel(pick.task)}, trial ${pick.trial}): ${pick.issues[0].reason.replace(/ \(bridges\)$/, "")}, marked in red. Open it.`;
  $("jump-trials").addEventListener("click", (event) => { if (plainClick(event)) { event.preventDefault(); scrollToResults(true); } });
}

// ---- why first prints don't pass ----

function renderWhy() {
  const entries = lookup.entries.get("first").filter((entry) => entry.counted);
  const notPassing = entries.filter((entry) => entry.verdict !== "pass").length;
  const reasons = reasonCounts(entries).filter((reason) => reason.kind === "failed" || reason.kind === "not graded").slice(0, 8);
  const most = Math.max(...reasons.map((reason) => reason.count), 1);
  $("why-sub").textContent = `${notPassing} of ${entries.length} first prints don't pass. These are the most common reasons, by number of designs; a design can have more than one. Each opens the designs behind it.`;
  const list = clear($("why-body"));
  for (const reason of reasons) {
    const verdict = ISSUE_VERDICT[reason.kind];
    list.append(h("li", {}, cellLink(`why ${reason.key}`, { reason: reason.key }, { trials: reason.count }, { class: `why-row ${VERDICT[verdict].cls}` }, [
      h("span", { class: "why-label" }, icon(VERDICT[verdict].icon), h("span", {}, reason.text)),
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
      h("th", { scope: "col", class: "num" }, "Per passing design", h("small", {}, "with test prints: API cost; print time and filament are slicer estimates, nothing was printed")))));
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
        h("span", { class: "cell-note cell-note-ng" }, `the person couldn't tell in ${test.cant_tell.trials} of ${test.trials}`)]
      : h("span", { class: "cell-none" }, "Not run with test prints");
    const per = test
      ? h("span", { class: "per" }, h("span", { class: "per-cost" }, money2(test.cost_per_pass)), h("span", {}, `est. ${hours1(test.est_print_s_per_pass)} printing`), h("span", {}, `est. ${grams(test.est_grams_per_pass)} filament`))
      : h("span", { class: "cell-none" }, "n/a");
    body.append(h("tr", {},
      h("th", { scope: "row" }, entry.short, h("small", {}, `${tokens(entry.tokens_per_trial)} tokens a trial`)),
      h("td", { "data-label": "First print" }, rate(`${entry.short}, first print`, entry.first, { cond: "first", task: "scored", model }), stoppedNote(entry.first.excluded)),
      h("td", { "data-label": "After one round of feedback" }, afterCell),
      h("td", { "data-label": "Test prints first" }, testCell),
      h("td", { "data-label": "Per passing design (est.)", class: "td-per num" }, per)));
  }
  table.append(body);

  const estoa = score.estoa_line.replace(/\*\*/g, "").replace(/\s*\(\[[^\]]*\]\(#[^)]*\)\)/g, "").replace(/1 of 30 designs pass/, "1 of 30 designs passes");
  const notes = h("div", { class: "notes" },
    h("p", { class: "bar-legend" },
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-pass" })), "pass"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-pass2" })), "pass on the second print"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-ng" })), "not graded (never a pass)"),
      h("span", { class: "key" }, h("span", { class: "bar bar-key", "aria-hidden": "true" }, h("span", { class: "bar-rest" })), "fail, declined or no design")),
    h("p", {}, "Sorted by pass rate with test prints first, then lower cost per passing design; the models not run that way follow, by first-print pass rate. ",
      `Models need ${score.min_trials} or more trials on each part to be listed with test prints. A cell's total is the number of trials saved for that model, which isn't always 40. ${score.skipped}`),
    h("p", {}, "The three columns aren't a ranking of methods: the test-prints-first column has fewer trials, and a pass after “I can't tell you how that one came out” may owe something to the model moving to a size the records cover."),
    h("p", {}, estoa, " ",
      stateLink({ cond: "first", task: score.harder_task }, {}, "First prints", { fromDefaults: true, toResults: true }), ", ",
      stateLink({ cond: "after_feedback", task: score.harder_task }, {}, "after feedback", { fromDefaults: true, toResults: true }), ", ",
      stateLink({ cond: "test_first", task: score.harder_task }, {}, "with test prints first", { fromDefaults: true, toResults: true }), "."));

  const host = $("scorecard-body");
  add(clear(host), h("div", { class: "table-scroll" }, table), notes);
  host.removeAttribute("aria-busy");
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
      h("h3", {}, entry.short),
      h("table", {},
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Part")), MULTI_CONDS.map(([, label]) => h("th", { scope: "col" }, label)))),
        h("tbody", {}, rows))));
  }
  host.removeAttribute("aria-busy");
}

// ---- header and footer ----

function renderFoot() {
  const repo = index.transcript_base.replace(/\/blob\/.*$/, "");
  $("repo-link").href = repo;
  add(clear($("foot")),
    h("p", {}, `${index.trials.length.toLocaleString("en-US")} saved entries`,
      index.commit ? [" from commit ", h("a", { href: `${repo}/commit/${index.commit}` }, h("code", {}, index.commit.slice(0, 7)))] : null,
      ". The scorecard's numbers are computed by the repository's own scorecard script from the saved runs, the same numbers as its README."),
    h("p", {}, h("a", { href: repo + "#readme" }, "The README"), " explains the parts, the test prints behind the checks and what couldn't be graded."));
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
  const meanings = h("details", { class: "meanings" }, h("summary", {}, "What these mean"),
    h("dl", {}, [...VERDICTS, "not counted"].map((name) => h("div", {}, h("dt", {}, VERDICT[name] ? badge(name, { small: true }) : h("span", { class: "tag tag-excluded" }, "Not counted")), h("dd", {}, index.definitions[name])))));

  // model and reason
  const models = lookup.modelOrder.filter((model) => groupEntries.some((entry) => entry.row.model === model && taskMatches(entry.row, state.task)));
  const pooledHere = pooledModels().some((model) => models.includes(model)) && models.some((model) => !pooledModels().includes(model));
  const modelSelect = h("select", { id: "f-model", "data-k": "model", class: state.model ? "is-set" : "" },
    h("option", { value: "" }, "All models"),
    pooledHere ? h("option", { value: POOLED, selected: state.model === POOLED }, `The ${pooledModels().length} models run all three ways`) : null,
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
  if (state.model) narrowed.push(state.model === POOLED ? `the ${pooledModels().length} models run all three ways` : modelShort(state.model));
  const picked = [];
  if (state.verdict) picked.push(state.verdict === "not-counted" ? "not counted" : VERDICT[verdictFromSlug(state.verdict)].label.toLowerCase());
  if (state.reason) picked.push(`reason: ${index.reason_groups[state.reason]}`);
  const scope = `${total.toLocaleString("en-US")} ${noun}${narrowed.length ? ` (${narrowed.join(", ")})` : ""}`;
  if (state.verdict === "not-counted") return `Showing ${shown.length} not counted, beside the ${scope}`;
  return picked.length ? `Showing ${shown.length.toLocaleString("en-US")} of ${scope}: ${picked.join("; ")}` : `Showing all ${scope}`;
}

function renderReasons() {
  const host = clear($("reasons"));
  const reasons = reasonCounts(scopeEntries(state).filter((entry) => verdictMatches(entry, state)));
  if (!reasons.length) return;
  const open = state.reason || ["fail", "not-graded"].includes(state.verdict);
  const settle = new Map(Object.values(index.not_graded_reasons).map((item) => [item.reason_group, item.settle]));
  const list = h("ul", { class: "reason-list" });
  for (const reason of reasons) {
    const pressed = state.reason === reason.key;
    list.append(h("li", {}, h("button", { type: "button", class: "reason", "aria-pressed": String(pressed), onclick: () => navigate({ reason: pressed ? "" : reason.key }) },
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
  const reason = row.issues[0] ? `. ${row.issues[0].reason}` : "";
  const how = state.cond === "after_feedback" ? (entry.via === "second" ? ", second print" : ", first print") : "";
  return `${row.model_short}, ${taskLabel(row.task)}, trial ${row.trial}${how}: ${VERDICT[entry.verdict].label}${reason}` + (isHeadline() && !entry.counted ? `. Not counted: ${row.excluded_reason}` : "");
}

function trialCard(entry) {
  const row = entry.row;
  const link = h("a", { class: `card ${VERDICT[entry.verdict].cls}`, href: hrefFor({ trial: row.slug }), "data-slug": row.slug, "aria-label": entryLabel(entry) },
    thumbBox(row),
    h("span", { class: "card-body" }, badge(entry.verdict, { small: true }), h("span", { class: "card-trial" }, `Trial ${row.trial}`), entryFlag(entry)));
  link.addEventListener("click", (event) => {
    if (!plainClick(event)) return;
    event.preventDefault();
    navigate({ trial: row.slug }, { opened: true });
  });
  return link;
}

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
    lines.push(h("ul", { class: "row-reasons" }, reasons.slice(0, 3).map((reason) => h("li", {}, h("button", {
      type: "button", class: "row-reason", "aria-pressed": String(state.reason === reason.key), title: "Show only the designs with this reason",
      onclick: () => navigate({ reason: state.reason === reason.key ? "" : reason.key }),
    }, h("b", {}, `${reason.count} ×`), " ", reason.text))), reasons.length > 3 ? h("li", { class: "row-more" }, `and ${plural(reasons.length - 3, "other reason")}`) : null));
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
  return h("section", { class: "model-row", "aria-label": `${modelShort(model)}, ${taskLabel(task)}` },
    h("div", { class: "model-head" },
      h("h4", {}, modelShort(model), showTask ? h("small", {}, taskLabel(task)) : null),
      h("p", { class: "model-stat" }, summary.stat),
      summary.cell ? bar(summary.cell, { split: state.cond === "after_feedback" }) : null,
      summary.lines),
    h("div", { class: "cards" }, entries.map(trialCard)));
}

// One line per model: a strip of verdict marks and the main reason. Opens that model's row of pictures.
function stripRow(task, model, entries) {
  const summary = rowSummary(task, model, entries);
  const top = reasonCounts(entries)[0];
  const marks = h("span", { class: "marks", "aria-hidden": "true" }, entries.map((entry) => h("span", { class: `mark ${VERDICT[entry.verdict].cls}` }, icon(VERDICT[entry.verdict].icon))));
  return stateLink({ task, model, show: "" }, { class: "strip", "aria-label": `${modelShort(model)}, ${taskLabel(task)}: ${verdictLine(countVerdicts(entries))}. Open these ${entries.length} designs.` }, [
    h("span", { class: "strip-model" }, modelShort(model)),
    h("span", { class: "strip-stat" }, summary.stat),
    marks,
    h("span", { class: "strip-reason" }, top ? [h("b", {}, `${top.count} ×`), " ", top.text] : ""),
    icon("next", "icon strip-go"),
  ]);
}

function taskHead(task, entries) {
  const info = index.tasks[task];
  const provided = state.cond === "after_feedback" ? countVerdicts(scopeEntries({ cond: state.cond, task, model: "" })) : index.counts[isHeadline() ? "counted" : "all"][state.cond]?.[task] || {};
  const line = state.verdict === "not-counted"
    ? `${entries.length} not counted, each with its reason`
    : state.model
      ? `${state.model === POOLED ? "These models" : modelShort(state.model)}: ${verdictLine(countVerdicts(scopeEntries({ cond: state.cond, task, model: state.model }).filter((entry) => countable(entry))))}`
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
  const strips = state.show === "strips" || (state.show !== "pictures" && entries.length > STRIPS_ABOVE);
  $("result-count").textContent = summaryText();
  const tools = clear($("result-tools"));
  if (entries.length > 12) {
    tools.append(h("button", { type: "button", class: "btn btn-small", onclick: () => navigate({ show: strips ? "pictures" : "strips" }, { replace: true }) },
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

const findCard = (slug) => document.querySelector(`.card[data-slug="${CSS.escape(slug)}"]`);

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
  box.append(h("p", {}, h("button", { type: "button", class: "btn", onclick: () => navigate({ task: "all", verdict: "", model: "", reason: "" }) }, "Clear the filters")));
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
  // After feedback: the entry points at the print whose verdict the scorecard counts.
  for (const item of lookup.entries.get("after_feedback")) same(`after feedback verdict of ${item.first.id}`, item.row.verdict, item.verdict);
  // Every link drawn on the page (headline tiles, reasons chart, scorecard cells, by-part bars) opens a list with
  // exactly the numbers the link shows.
  let links = 0;
  for (const link of linkChecks.values()) {
    const list = selectEntries({ ...DEFAULTS, ...link.patch });
    links += 1;
    same(`link “${link.label}” trials`, list.length, link.trials);
    if ("passes" in link) same(`link “${link.label}” passes`, list.filter((item) => item.verdict === "pass").length, link.passes);
  }
  const result = { compared, links, problems };
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
  if (!state.trial && ["cond", "task", "verdict", "model", "reason"].some((key) => params.has(key))) scrollToResults(false);
  performance.mark("trials-painted");
  verifyCounts();
}

start();
