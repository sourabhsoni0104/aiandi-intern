"""Build report.html: each comment with Clef's label, easy to scan and to check.

The page is one self-contained file that works offline. All comment text is
HTML-escaped here, so nothing written in a comment can run on the page. A small
script adds filters, sorting and a review checklist: mark each of Clef's labels
right or wrong as you read, and the page turns your marks and notes into
MISTAKES.md. Marks are kept only in the reviewer's own browser.
"""

import html
import re
from datetime import datetime

esc = html.escape


def write_report(path, *, comments, answers, model, labels, course, forum, answered_at,
                 low_confidence):
    """Write the page for `comments`; `answers` maps a comment id to Clef's answer."""
    rows, counts, low = [], dict.fromkeys(labels, 0), 0
    for comment in comments:
        answer = answers.get(comment["id"])
        rows.append(_row(comment, answer, labels, low_confidence))
        if answer:
            counts[answer["choice"]] = counts.get(answer["choice"], 0) + 1
            low += answer["confidence"] < low_confidence
    missing = sum(c["id"] not in answers for c in comments)

    chips = [_chip("all", "all", len(comments), pressed=True)]
    chips += [_chip(label, label, count) for label, count in counts.items()]
    chips.append(_chip("low", f"⚠ confidence below {low_confidence:.2f}", low))
    if missing:
        chips.append(_chip("unclassified", "not classified", missing))

    if answered_at:
        when = datetime.fromisoformat(answered_at)
        when = f"answers from {when.day} {when:%b %Y, %H:%M} UTC"
    else:
        when = "not classified yet"
    values = {
        "MODEL": esc(model),
        "LABELS": esc(" ".join(labels)),
        "COURSE": esc(course),
        "FORUM": esc(forum),
        "TOTAL": str(len(comments)),
        "WHEN": esc(when),
        "THRESHOLD": f"{low_confidence:.2f}",
        "CHIPS": "\n    ".join(chips),
        "ROWS": "\n".join(rows),
    }
    # One pass, so text inside a comment is never itself treated as a placeholder.
    page = re.sub(r"__([A-Z]+)__", lambda match: values[match.group(1)], PAGE)
    path.write_text(page, encoding="utf-8")


def _chip(value, text, count, pressed=False):
    dot = "" if value in ("all", "low") else "<i></i>"
    return (f'<button type="button" class="chip {esc(value)}" data-filter="{esc(value)}" '
            f'aria-pressed="{str(pressed).lower()}">{dot}{esc(text)} <b>{count}</b></button>')


def _row(comment, answer, labels, low_confidence):
    if answer is None:
        label, confidence, low = "unclassified", -1.0, False
        verdict = '<span class="badge">not classified</span>'
        review = ""
    else:
        label, confidence = answer["choice"], answer["confidence"]
        low = confidence < low_confidence
        probabilities = answer["probabilities"]
        breakdown = ", ".join(f"{name} {probabilities.get(name, 0):.2f}" for name in labels)
        segments = "".join(
            f'<span class="seg {esc(name)}" style="width:{probabilities.get(name, 0) * 100:.1f}%"></span>'
            for name in labels
        )
        second = max((name for name in labels if name != label), key=lambda n: probabilities.get(n, 0))
        warning = "⚠ " if low else ""
        verdict = (
            f'<span class="badge">{esc(label)}</span>\n'
            f'    <span class="conf{" low" if low else ""}" title="Clef\'s confidence, from 0 to 1">'
            f'{warning}confidence {confidence:.2f}</span>\n'
            f'    <span class="bar" role="img" title="{esc(breakdown)}" aria-label="{esc(breakdown)}">'
            f'{segments}</span>\n'
            f'    <span class="alt">next: {esc(second)} {probabilities.get(second, 0):.2f}</span>'
        )
        options = "".join(f'<option value="{esc(n)}">{esc(n)}</option>' for n in labels if n != label)
        review = f"""
  <div class="review">
    <div class="verdicts" role="group" aria-label="Is Clef's label right for comment {comment['id']}?">
      <button type="button" data-verdict="right" aria-pressed="false">✓ Right</button><button type="button" data-verdict="wrong" aria-pressed="false">✗ Wrong</button>
    </div>
    <label class="check"><input type="checkbox" class="borderline"> Borderline</label>
    <label class="fix">Should be <select>{options}</select></label>
    <textarea class="note" rows="2" aria-label="Why, for comment {comment['id']}" placeholder="Why? One or two sentences."></textarea>
  </div>"""
    search = " ".join((f"#{comment['id']}", comment["comment"], comment["author"], comment["thread"]))
    return f"""<article class="row {esc(label)}" data-id="{comment['id']}" data-label="{esc(label)}" data-confidence="{confidence:.4f}" data-low="{int(low)}" data-search="{esc(search.lower())}">
  <div class="id">#{comment['id']}</div>
  <div class="verdict">
    {verdict}
  </div>
  <div class="body">
    <p class="text">{esc(comment['comment'])}</p>
    <p class="meta">{esc(comment['author'])} · {esc(comment['thread'])} · {esc(comment['posted_at'])}</p>
  </div>{review}
</article>"""


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clef moderation report</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f5f6f8; --panel: #ffffff; --text: #1c2129; --muted: #5b6573; --line: #dfe3e8;
    --hover: #eef1f4; --accent: #2357c6; --warn: #9a5b00;
    --acceptable: #22764a; --acceptable-soft: #e2f2e9;
    --toxic: #bb2d22; --toxic-soft: #fbe6e4;
    --spam: #9a5b00; --spam-soft: #fcefd9;
    --unclassified: #6b7280; --unclassified-soft: #eceef1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121418; --panel: #1b1e24; --text: #e5e8ec; --muted: #9ba4af; --line: #2d323a;
      --hover: #252930; --accent: #85a9ff; --warn: #f2b45f;
      --acceptable: #6cc995; --acceptable-soft: #1a3325;
      --toxic: #ff8f85; --toxic-soft: #3c1f1c;
      --spam: #f2b45f; --spam-soft: #3a2b14;
      --unclassified: #9ca3af; --unclassified-soft: #2a2e35;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
  }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  header { background: var(--panel); border-bottom: 1px solid var(--line); padding: 14px 20px 10px; }
  @media (min-width: 760px) { header { position: sticky; top: 0; z-index: 1; } }
  h1 { margin: 0; font-size: 1.25rem; }
  .sub { margin: 2px 0 0; color: var(--muted); font-size: .875rem; }
  code { font: .85em ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--hover);
         padding: 1px 5px; border-radius: 4px; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
  button, input, select, textarea { font: inherit; color: inherit; }
  .chip, .button {
    border: 1px solid var(--line); background: var(--panel); border-radius: 999px;
    padding: 3px 12px; font-size: .875rem; cursor: pointer;
    display: inline-flex; gap: 6px; align-items: center;
  }
  .button { border-radius: 6px; }
  .button.primary { background: var(--accent); border-color: var(--accent); color: var(--panel); font-weight: 600; }
  .chip:hover, .button:hover { background: var(--hover); }
  .button.primary:hover { background: var(--accent); filter: brightness(1.1); }
  .chip[aria-pressed="true"] { border-color: var(--text); background: var(--hover); font-weight: 600; }
  .chip b { font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; }
  .chip i { width: 9px; height: 9px; border-radius: 50%; background: var(--c); }
  .chip.low { color: var(--warn); }
  input[type="search"], select, textarea {
    background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px;
  }
  input[type="search"] { flex: 1 1 220px; max-width: 380px; }
  .toolbar label { font-size: .875rem; color: var(--muted); }
  #progress { font-size: .875rem; font-weight: 600; font-variant-numeric: tabular-nums; margin-right: auto; }
  main { max-width: 1240px; margin: 0 auto; padding: 12px 20px 48px; }
  .help { color: var(--muted); font-size: .85rem; margin: 4px 0 12px; max-width: 70rem; }

  .acceptable { --c: var(--acceptable); --soft: var(--acceptable-soft); }
  .toxic { --c: var(--toxic); --soft: var(--toxic-soft); }
  .spam { --c: var(--spam); --soft: var(--spam-soft); }
  .unclassified { --c: var(--unclassified); --soft: var(--unclassified-soft); }
  .row {
    display: grid; grid-template-columns: 2.8rem 10rem minmax(0, 1fr) 14.5rem; gap: 6px 16px;
    align-items: start; background: var(--panel); border: 1px solid var(--line);
    border-left: 5px solid var(--c, var(--line)); border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;
  }
  .row[hidden] { display: none; }
  .row[data-review="right"] { opacity: .6; }
  .row[data-review="right"]:hover, .row[data-review="right"]:focus-within { opacity: 1; }
  .row[data-review="wrong"] { outline: 2px solid var(--toxic); outline-offset: -1px; }
  .id { color: var(--muted); font-size: .875rem; font-variant-numeric: tabular-nums; padding-top: 2px; }
  .verdict { display: flex; flex-direction: column; gap: 4px; font-size: .8rem; }
  .badge {
    align-self: flex-start; font-size: .75rem; font-weight: 700; letter-spacing: .05em;
    text-transform: uppercase; color: var(--c); background: var(--soft); border-radius: 4px; padding: 1px 8px;
  }
  .conf, .alt { color: var(--muted); font-variant-numeric: tabular-nums; }
  .conf.low { color: var(--warn); font-weight: 700; }
  .bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--line); }
  .seg { background: var(--c); }
  .text { margin: 0; overflow-wrap: anywhere; }
  .meta { margin: 3px 0 0; color: var(--muted); font-size: .8rem; }
  .review { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; font-size: .8rem; }
  .verdicts { display: inline-flex; }
  .verdicts button {
    border: 1px solid var(--line); background: var(--panel); padding: 3px 10px; cursor: pointer;
  }
  .verdicts button:first-child { border-radius: 6px 0 0 6px; }
  .verdicts button:last-child { border-radius: 0 6px 6px 0; border-left: 0; }
  .verdicts button:hover { background: var(--hover); }
  [data-verdict="right"][aria-pressed="true"] {
    background: var(--acceptable-soft); color: var(--acceptable); font-weight: 700;
  }
  [data-verdict="wrong"][aria-pressed="true"] { background: var(--toxic-soft); color: var(--toxic); font-weight: 700; }
  .check { display: inline-flex; gap: 4px; align-items: center; cursor: pointer; }
  .fix, .note { display: none; }
  .row[data-review="wrong"] .fix { display: inline-flex; gap: 6px; align-items: center; }
  .row[data-review="wrong"] .note, .row.is-borderline .note { display: block; width: 100%; resize: vertical; }
  #empty { color: var(--muted); text-align: center; padding: 32px; }

  dialog {
    width: min(780px, calc(100vw - 32px)); border: 1px solid var(--line); border-radius: 10px;
    background: var(--panel); color: var(--text); padding: 18px 20px;
  }
  dialog::backdrop { background: rgb(0 0 0 / .45); }
  dialog h2 { margin: 0 0 4px; font-size: 1.1rem; }
  #markdown { width: 100%; height: 55vh; font: .8rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
  .dialog-buttons { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }

  @media (max-width: 760px) {
    header, main { padding-left: 16px; padding-right: 16px; }
    .row { grid-template-columns: 2.4rem minmax(0, 1fr); padding: 10px 12px; }
    .verdict { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
    .bar { width: 5rem; }
    .body, .review { grid-column: 2; }
  }
</style>
</head>
<body data-model="__MODEL__" data-labels="__LABELS__">
<header>
  <h1>Clef moderation report</h1>
  <p class="sub">__COURSE__ · forum: __FORUM__</p>
  <p class="sub">Model <code>__MODEL__</code> on Cloudflare Workers AI · __TOTAL__ comments · __WHEN__</p>
  <nav class="toolbar" aria-label="Show comments by Clef's label">
    __CHIPS__
  </nav>
  <div class="toolbar">
    <input type="search" id="search" placeholder="Search text, author, or #id" aria-label="Search comments">
    <label>Sort
      <select id="sort">
        <option value="id">by comment id</option>
        <option value="confidence">least confident first</option>
        <option value="label">by label, least confident first</option>
      </select>
    </label>
  </div>
  <div class="toolbar">
    <span id="progress" aria-live="polite"></span>
    <label class="check"><input type="checkbox" id="unchecked"> Only unchecked</label>
    <button type="button" class="button primary" id="export">Export MISTAKES.md</button>
    <button type="button" class="button" id="reset">Reset marks</button>
  </div>
</header>
<main>
  <p class="help">
    The coloured bar shows Clef's probability for each label; hover it for the numbers.
    <b>Confidence</b> is Clef's own certainty from 0 to 1, and ⚠ marks answers below __THRESHOLD__,
    the ones most worth a careful look. To check Clef's work, read each comment and mark it
    <b>✓ Right</b> or <b>✗ Wrong</b> (then pick the right label and say why); tick <b>Borderline</b>
    for close calls. Your marks are saved in this browser only. <b>Export</b> turns them into MISTAKES.md.
  </p>
  <div id="rows">
__ROWS__
  </div>
  <p id="empty" hidden>No comments match.</p>
</main>
<dialog id="dialog" aria-labelledby="dialog-title">
  <form method="dialog">
    <h2 id="dialog-title">MISTAKES.md</h2>
    <p class="help">Made from your marks and notes. Copy it into MISTAKES.md, or download it, and edit it as you like.</p>
    <textarea id="markdown" readonly aria-label="MISTAKES.md contents"></textarea>
    <div class="dialog-buttons">
      <button type="button" class="button" id="copy">Copy</button>
      <button type="button" class="button" id="download">Download</button>
      <button class="button primary" value="close">Close</button>
    </div>
  </form>
</dialog>
<script>
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const model = document.body.dataset.model;
  const labelOrder = document.body.dataset.labels.split(" ");
  const KEY = `clef-review:${model}`;
  const list = $("rows");
  const rows = [...list.querySelectorAll(".row")];
  const checkable = rows.filter((row) => row.querySelector(".review"));
  const view = { filter: "all", query: "", uncheckedOnly: false };

  // Marks live in localStorage, keyed by comment id. A mark made against a label Clef has
  // since changed (a re-run with new criteria) loses its right/wrong verdict.
  let marks = {};
  try { marks = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { marks = {}; }
  const save = () => {
    try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) { /* storage blocked: marks last until the tab closes */ }
  };
  const markOf = (row) => marks[row.dataset.id] || {};
  const editMark = (row) =>
    (marks[row.dataset.id] ||= { label: row.dataset.label, verdict: "", fix: "", borderline: false, note: "" });

  function paint(row) {
    const mark = markOf(row);
    row.dataset.review = mark.verdict || "";
    row.classList.toggle("is-borderline", !!mark.borderline);
    for (const button of row.querySelectorAll("[data-verdict]")) {
      button.setAttribute("aria-pressed", String(button.dataset.verdict === mark.verdict));
    }
    row.querySelector(".borderline").checked = !!mark.borderline;
    if (mark.fix) row.querySelector(".fix select").value = mark.fix;
    row.querySelector(".note").value = mark.note || "";
  }

  function showProgress() {
    const all = checkable.map(markOf);
    const checked = all.filter((m) => m.verdict).length;
    const wrong = all.filter((m) => m.verdict === "wrong").length;
    const borderline = all.filter((m) => m.borderline).length;
    $("progress").textContent =
      `Checked ${checked} of ${checkable.length} · ${wrong} wrong · ${borderline} borderline`;
  }

  function applyFilter() {
    const query = view.query.trim().toLowerCase();
    let shown = 0;
    for (const row of rows) {
      const d = row.dataset;
      const match =
        (view.filter === "all" || (view.filter === "low" ? d.low === "1" : d.label === view.filter)) &&
        (!query || d.search.includes(query)) &&
        (!view.uncheckedOnly || !d.review);
      row.hidden = !match;
      if (match) shown++;
    }
    $("empty").hidden = shown > 0;
  }

  function sortRows(how) {
    const id = (row) => Number(row.dataset.id);
    const confidence = (row) => Number(row.dataset.confidence);
    const label = (row) => labelOrder.indexOf(row.dataset.label);
    const keys = { id: [id], confidence: [confidence, id], label: [label, confidence, id] }[how];
    const compare = (a, b) => {
      for (const key of keys) { const diff = key(a) - key(b); if (diff) return diff; }
      return 0;
    };
    list.append(...rows.slice().sort(compare));
  }

  function markdown() {
    const oneLine = (s) => (s || "").replace(/\\s+/g, " ").trim();
    const why = (row) => oneLine(markOf(row).note) || "TODO: one or two sentences on why.";
    const entry = (row, heading, lines) =>
      [`### ${heading}`, "", `> ${oneLine(row.querySelector(".text").textContent)}`, "", ...lines, ""];
    const wrong = checkable.filter((row) => markOf(row).verdict === "wrong");
    const agreed = checkable.filter((row) => markOf(row).verdict === "right" && markOf(row).borderline);
    const checked = checkable.filter((row) => markOf(row).verdict).length;
    const out = [
      "# Clef's mistakes", "",
      `Model: \\`${model}\\` on Cloudflare Workers AI. Checked ${checked} of ${checkable.length} comments; ` +
        `Clef got ${wrong.length} wrong.`, "",
      "## Mistakes", "",
    ];
    if (!wrong.length) out.push("None marked.", "");
    for (const row of wrong) {
      out.push(...entry(row, `Comment ${row.dataset.id}${markOf(row).borderline ? " (borderline)" : ""}`, [
        `- **Clef's label:** ${row.dataset.label}`,
        `- **Right label:** ${row.querySelector(".fix select").value}`,
        `- **Why:** ${why(row)}`,
      ]));
    }
    if (agreed.length) {
      out.push("## Borderline, but Clef's label is right", "");
      for (const row of agreed) {
        out.push(...entry(row, `Comment ${row.dataset.id} (borderline)`, [
          `- **Clef's label and the right label:** ${row.dataset.label}`,
          `- **Why:** ${why(row)}`,
        ]));
      }
    }
    return out.join("\\n");
  }

  for (const row of checkable) {
    const mark = marks[row.dataset.id];
    if (mark && mark.label !== row.dataset.label) Object.assign(mark, { label: row.dataset.label, verdict: "", fix: "" });
    paint(row);
  }
  showProgress();

  list.addEventListener("click", (event) => {
    const button = event.target.closest("[data-verdict]");
    if (!button) return;
    const row = button.closest(".row");
    const mark = editMark(row);
    mark.verdict = mark.verdict === button.dataset.verdict ? "" : button.dataset.verdict; // second click undoes
    save(); paint(row); showProgress();
    if (mark.verdict === "wrong") row.querySelector(".note").focus();
  });
  list.addEventListener("change", (event) => {
    const row = event.target.closest(".row");
    if (event.target.matches(".borderline")) {
      editMark(row).borderline = event.target.checked;
      save(); paint(row); showProgress();
    } else if (event.target.matches(".fix select")) {
      editMark(row).fix = event.target.value;
      save();
    }
  });
  list.addEventListener("input", (event) => {
    if (!event.target.matches(".note")) return;
    editMark(event.target.closest(".row")).note = event.target.value;
    save();
  });

  for (const chip of document.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      view.filter = chip.dataset.filter;
      for (const other of document.querySelectorAll(".chip")) other.setAttribute("aria-pressed", String(other === chip));
      applyFilter();
    });
  }
  $("search").addEventListener("input", (event) => { view.query = event.target.value; applyFilter(); });
  $("sort").addEventListener("change", (event) => sortRows(event.target.value));
  $("unchecked").addEventListener("change", (event) => { view.uncheckedOnly = event.target.checked; applyFilter(); });

  $("export").addEventListener("click", () => { $("markdown").value = markdown(); $("dialog").showModal(); });
  $("copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("markdown").value); }
    catch (e) { $("markdown").select(); document.execCommand("copy"); }
    $("copy").textContent = "Copied ✓";
    setTimeout(() => { $("copy").textContent = "Copy"; }, 1500);
  });
  $("download").addEventListener("click", () => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([$("markdown").value + "\\n"], { type: "text/markdown" }));
    link.download = "MISTAKES.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  $("reset").addEventListener("click", () => {
    if (!confirm("Clear all your ✓/✗ marks and notes on this page?")) return;
    marks = {};
    save(); checkable.forEach(paint); showProgress(); applyFilter();
  });
})();
</script>
</body>
</html>
"""
