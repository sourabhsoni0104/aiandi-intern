# Notes

## How to run

You need Python 3.8 or newer. The program uses only the standard library, so there is
nothing to install.

1. Copy `cloud-flare.sh` to `cloud-flare.local.sh` and put your Cloudflare account ID and
   a Workers AI API token in it. `.gitignore` keeps that file out of git.
2. Classify the comments and build the page:

   ```sh
   python3 classify.py
   ```

   This asks Clef about every comment in `comments.json`, saves Clef's answers in
   `results-clef.json`, and writes `report.html`.
3. Open `report.html` in a browser.

Other options:

| Command | What it does |
| --- | --- |
| `python3 classify.py --limit 3` | Classify only 3 comments: a cheap check that your credentials work. Run again without `--limit` to do the rest. |
| `python3 classify.py --model clef-flash` | Use the smaller, faster model. Its answers go in `results-clef-flash.json`. |
| `python3 classify.py --fresh` | Ignore the saved answers and ask Clef again. |
| `python3 classify.py --report-only` | Rebuild `report.html` from the saved answers without calling the API. |
| `python3 classify.py --review-below 0.6` | Change the confidence below which a label is flagged ⚠ for a careful look (default 0.5). |

## How it works

- `classify.py` sends one request per comment, four at a time. Clef's input is the
  comment, its author and its thread; the question is a single *choice* between
  acceptable, toxic and spam. The instructions and the description of each label are at
  the top of `classify.py`.
- Answers are saved as they arrive. If a run stops (rate limit, network, Ctrl-C),
  running it again only asks about the comments that are left. If the instructions or
  label descriptions change, the saved answers no longer apply and every comment is
  asked again.
- Rate limits (HTTP 429), server errors and timeouts are retried with backoff. A bad
  account ID or token stops the run at once with a clear message.
- `report.py` writes `report.html`: one row per comment, coloured by Clef's label, with
  Clef's confidence and the probability of each label. You can filter by label or by low
  confidence, search, and sort with the least confident first.
- The page also has a checklist for checking Clef by hand: mark each label ✓ right or
  ✗ wrong, choose the right label and write why, then **Export MISTAKES.md** puts those
  marks in the MISTAKES.md format. Marks are kept only in your own browser. The page
  works offline, and all comment text is escaped, so nothing in a comment can run as code.

## Tools and models used

- Cloudflare Workers AI, model `clef` (Cloudflare's decision model), to classify the
  comments.
- Python 3, standard library only.
- Claude for code-writing, Codex for checking: the AI assistant used to write the program.

## What I felt about doing this

It was a fun experience and it took me about 22 mins completing this, in which 18min 32 seconds were for claude making it and testing, and remaining were just codex checking. I learnt a new thing doing the task.
