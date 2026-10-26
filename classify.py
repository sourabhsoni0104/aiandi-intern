#!/usr/bin/env python3
"""Classify forum comments as acceptable, toxic or spam with Cloudflare's Clef.

    python3 classify.py                     # classify every comment, write results-clef.json and report.html
    python3 classify.py --limit 3           # only the first 3 comments: a cheap check of your credentials
    python3 classify.py --model clef-flash  # use the faster, cheaper model
    python3 classify.py --fresh             # ignore saved answers and ask Clef again
    python3 classify.py --report-only       # rebuild report.html from saved answers, no API calls

Clef's answers are saved in results-<model>.json and reused while the question
(instructions and criteria) stays the same, so an interrupted run picks up where
it stopped. Credentials come from cloud-flare.local.sh (see README.md),
or from the CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN environment variables.
Standard library only: nothing to install.
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import report

HERE = Path(__file__).resolve().parent
COMMENTS_FILE = HERE / "comments.json"
CREDENTIALS_FILE = HERE / "cloud-flare.local.sh"
REPORT_FILE = HERE / "report.html"

API_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
MODELS = ("clef", "clef-flash")
PLACEHOLDERS = {"0123456789abcdef0123456789abcdef", "your-cloudflare-api-token-goes-here"}
WORKERS = 4        # requests in flight at once
MAX_ATTEMPTS = 5   # per comment, for rate limits (HTTP 429), server errors and timeouts

# The question Clef answers for each comment. `comment`, `author` and `thread` are
# the named fields of the request's state; {course} and {forum} come from comments.json.
INSTRUCTIONS = (
    "`comment` was posted by `author` in the `thread` thread of the discussion forum for "
    "{course}, in the section \"{forum}\". Decide whether a moderator should keep `comment` "
    "(acceptable), remove it as abuse (toxic), or remove it as spam. Judge what `comment` "
    "says and why it was posted; use `author` and `thread` only as context. Students write "
    "informally, often in Indian English or Hinglish and with emoji; that alone is never a "
    "reason to remove a comment."
)
CRITERIA = {
    "acceptable": (
        "Keep. A genuine post from someone taking part in the course: questions, answers, "
        "tips, sharing their work, feedback on other people's work (including pointing out "
        "bugs), thanks, apologies, and requests about deadlines, extensions or grades. Also "
        "keep criticism of and complaints about the course, assignment, grading or AI tools, "
        "and disagreement with other posters, even when blunt or negative, as long as it "
        "does not insult, mock or threaten anyone."
    ),
    "toxic": (
        "Remove as abuse. Attacks people instead of discussing the work: insults or "
        "name-calling, mocking someone or their work to humiliate them, shaming accusations "
        "against a person, threats or intimidation, or demeaning generalisations about a "
        "group (gender, region, caste, religion, community, branch of study, and so on). "
        "This applies whether the target is a student, the TA, the teacher or the forum as a "
        "whole, and even when the post also makes a fair point."
    ),
    "spam": (
        "Remove as spam. Unsolicited promotion or scams that are not part of taking the "
        "course: selling products or services, paid assignment or exam help, ready-made "
        "solutions, notes or leaked papers, money-making schemes, crypto tips, jobs that ask "
        "for a fee, giveaways, referral codes, buying followers, or urging readers to contact "
        "a phone number, link, group or account to buy, join or sign up for something."
    ),
}


class ClefError(Exception):
    """A failure that retrying will not fix, or that kept happening after retries."""


def load_credentials():
    """Return (account_id, api_token) from the environment or cloud-flare.local.sh."""
    found = {}
    if CREDENTIALS_FILE.exists():
        text = CREDENTIALS_FILE.read_text(encoding="utf-8")
        found.update(re.findall(r"""^\s*(?:export\s+)?(\w+)=["']?([^"'\s]*)""", text, re.M))
    for name in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        if os.environ.get(name):
            found[name] = os.environ[name]
    account = found.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = found.get("CLOUDFLARE_API_TOKEN", "")
    if not account or not token or {account, token} & PLACEHOLDERS:
        sys.exit(
            "No Cloudflare credentials yet. Copy cloud-flare.sh to cloud-flare.local.sh and put\n"
            "your account ID and a Workers AI API token in it (README.md, step 3)."
        )
    return account, token


def ask_clef(comment, question, model, account, token):
    """Ask Clef to label one comment. Returns (answer, input_tokens_used)."""
    payload = {
        "model": model,
        "state": {field: comment[field] for field in ("comment", "author", "thread")},
        "questions": {"label": question},
    }
    request = urllib.request.Request(
        API_URL.format(account=account, model=model),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_after = None
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            if error.code in (401, 403):
                raise ClefError(
                    f"HTTP {error.code}: Cloudflare rejected the account ID or API token "
                    f"(the token needs Workers AI Read and Edit permissions). {detail}"
                ) from None
            if error.code != 429 and error.code < 500:
                raise ClefError(f"HTTP {error.code} for comment {comment['id']}: {detail}") from None
            problem, retry_after = f"HTTP {error.code}", error.headers.get("Retry-After")
        except OSError as error:  # network trouble or a timeout
            problem = str(getattr(error, "reason", error))
        if attempt == MAX_ATTEMPTS:
            raise ClefError(f"comment {comment['id']} still failing after {attempt} attempts ({problem})")
        if retry_after and retry_after.isdigit():
            time.sleep(int(retry_after))
        else:
            time.sleep(2 ** attempt + random.random())
    if not data.get("success"):
        raise ClefError(f"comment {comment['id']}: {data.get('errors')}")
    result = data["result"]
    return result["answers"]["label"], result.get("usage", {}).get("input_tokens", 0)


def classify(comments, model, question, account, token, answers):
    """Ask Clef about each comment, adding to `answers` (id -> answer) as replies arrive."""
    used = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(ask_clef, c, question, model, account, token): c for c in comments}
        try:
            for done, future in enumerate(as_completed(futures), 1):
                comment = futures[future]
                answer, tokens = future.result()
                answers[comment["id"]] = {
                    "id": comment["id"],
                    "choice": answer["choice"],
                    "probabilities": answer["probabilities"],
                    "confidence": answer["confidence"],
                }
                used += tokens
                text = comment["comment"]
                snippet = text[:60] + ("…" if len(text) > 60 else "")
                print(f"  {done:3}/{len(comments)}  #{comment['id']:<3} "
                      f"{answer['choice']:<10} {answer['confidence']:.2f}  {snippet}")
        except BaseException:
            for future in futures:  # don't send the requests still waiting in the queue
                future.cancel()
            raise
    print(f"Done. Clef read {used:,} input tokens.")


def results_file(model):
    return HERE / f"results-{model}.json"


def save_results(model, question, answers):
    """Write answers to results-<model>.json, via a temporary file so a crash can't corrupt
    it. Returns the time saved."""
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = {
        "model": model,
        "question": question,
        "saved_at": saved_at,
        "results": [answers[i] for i in sorted(answers)],
    }
    path = results_file(model)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return saved_at


def parse_args():
    parser = argparse.ArgumentParser(
        description="Classify comments.json with Cloudflare's Clef and write report.html."
    )
    parser.add_argument("--model", choices=MODELS, default="clef",
                        help="clef (larger, more accurate; the default) or clef-flash (faster, cheaper)")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore saved answers and ask Clef about every comment again")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="ask about at most N comments this run (handy for a first test)")
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild report.html from the saved answers without calling Clef")
    parser.add_argument("--review-below", type=float, default=0.5, metavar="C",
                        help="flag answers with confidence below C for a careful look (default 0.5)")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main():
    args = parse_args()
    model = args.model
    forum = json.loads(COMMENTS_FILE.read_text(encoding="utf-8"))
    comments = forum["comments"]
    path = results_file(model)
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    question = {
        "type": "choice",
        "instructions": INSTRUCTIONS.format(course=forum["course"], forum=forum["forum"]),
        "criteria": CRITERIA,
    }
    answers, answered_at, stopped = {}, None, None

    if args.report_only:
        if saved is None:
            sys.exit(f"No {path.name} yet: run without --report-only first.")
        question = saved["question"]
    elif saved and not args.fresh and saved["question"] != question:
        print(f"The question has changed since {path.name} was saved, so asking Clef again.")
        saved = None
    if saved and (args.report_only or not args.fresh):
        answers = {a["id"]: a for a in saved["results"]}
        answered_at = saved["saved_at"]

    todo = [] if args.report_only else [c for c in comments if c["id"] not in answers][:args.limit]
    if todo:
        account, token = load_credentials()
        print(f"Asking {model} about {len(todo)} comments "
              f"({len(answers)} already answered in {path.name})...")
        try:
            classify(todo, model, question, account, token, answers)
        except ClefError as error:
            stopped = str(error)
        except KeyboardInterrupt:
            stopped = "interrupted"
        finally:
            if answers:  # an early failure must not wipe out answers saved before
                answered_at = save_results(model, question, answers)
    elif not args.report_only:
        print(f"All {len(comments)} comments already have answers in {path.name} "
              "(use --fresh to ask again).")

    labels = tuple(question["criteria"])
    report.write_report(
        REPORT_FILE,
        comments=comments,
        answers=answers,
        model=model,
        labels=labels,
        course=forum["course"],
        forum=forum["forum"],
        answered_at=answered_at,
        low_confidence=args.review_below,
    )
    shown = [answers[c["id"]] for c in comments if c["id"] in answers]
    counts = Counter(a["choice"] for a in shown)
    low = sum(a["confidence"] < args.review_below for a in shown)
    print(f"Wrote {REPORT_FILE.name}: " + ", ".join(f"{counts[l]} {l}" for l in labels)
          + f"; {low} below confidence {args.review_below:.2f}"
          + f"; {len(comments) - len(shown)} not classified yet.")
    if stopped:
        sys.exit(f"Stopped early: {stopped}\n"
                 f"{len(shown)} of {len(comments)} comments have answers; run again to continue.")


if __name__ == "__main__":
    main()
