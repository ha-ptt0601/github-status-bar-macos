---
name: chip
description: Use when the user runs /chip or asks which PRs are waiting for their review (in English or Vietnamese, e.g. "which PRs need my review", "review inbox") and wants to pick some to review with /my-review-skill.
---

# chip — PR review inbox

`~/work/chip/bin/chip` does all the data work. You only pass its JSON to AskUserQuestion, collect the picks, and run the review loop. Never build, re-sort or filter options yourself, never reword them, and never print the PR list as a table.

The main way to pick PRs is **in the prompt bar**: the `chip` MCP server exposes every waiting PR as a resource, so typing `@` (or `@chip:`) followed by a few letters of the repo, number or title shows them in the autocomplete. The user can mention several.

Args:
- **Args contain `pr://`** (e.g. `/chip @chip:pr://shopbox-api/274-fix-orders… @chip:pr://api/2069-…`): run `~/work/chip/bin/chip pick "<args verbatim>"` and go straight to step 4 (review loop) with its output. Show no menus. If it exits 2, show stderr and tell the user the list may be stale; they can ask to reload, which runs `chip repos --refresh --force`, and mention again.
- **No args**: reply with exactly one line, "Type `/chip @` then a repo name, PR number or keyword to pick PRs (several allowed), and press Enter to review. For menus: `/chip menu`." and stop.
- `/chip menu [words]`: the in-chat menus below (steps 1–3). With words, skip step 1 and start step 2 with `--q "<words>"`.
- `/chip terminal`: run `~/work/chip/bin/chip open`, which opens the fzf picker in a new Terminal window. Reply with its stdout (or stderr on failure) and stop.

## 1. Choose the project (one keystroke)

```bash
~/work/chip/bin/chip repos --refresh     # fetches from GitHub (~5s), or reuses a fetch < 3 min old; add --force if the user asks to reload
                                         # later in the flow: `chip repos` (no --refresh) reuses the same fetch
```

Output: `{total, hidden: {approved, draft}, updated, questions}`. `questions` holds ONE single-select question: `All` plus the 3 busiest repos. The other repos are listed in the question text for typing.

- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- `total == 0`: "Inbox zero 🎉" plus the hidden counts, then stop.
- Otherwise, print one line, `<total> PRs waiting for you (hidden: <approved> approved, <draft> drafts · updated <updated>)`. Then call **AskUserQuestion with `questions` exactly as given**.
- Answer `All`: no filter. A repo label: `--repo <label>`. Other text: if it equals or contains a repo name from the question, use `--repo <that name>`; otherwise use `--q "<text>"`.

## 2. Tick PRs

```bash
~/work/chip/bin/chip menu --cached [--repo a] [--q "<words>"] [--page N]
```

(For `/chip menu <words>`, where step 1 was skipped, the first call is `chip menu --q "<words>"` without `--cached`. It fetches from GitHub.)

The output is `{page, pages, total, filter, hidden, questions}`. Call **AskUserQuestion with `questions` exactly as given**. If `total == 0`, say "No PRs match `<filter>`" and go back to step 1.

When the result has **16 PRs or fewer**, `questions` contains only multi-select PR questions and no nav question: the user ticks and submits once. Collect the ticked labels, ignoring `None`, and go straight to step 3. If an Other answer holds text instead, treat that text like the Other answer of step 1 (switch project or search), keep the labels ticked so far, and rerun this step.

When the result has **more than 16 PRs**, there are pages of 12 plus a nav question "Next?". Keep the filter state and **every label picked so far** across pages:

| Nav answer | Do |
|---|---|
| `Next page` | the same command with `--page <page+1>` |
| `Change project` | step 1 again, using `chip repos` without `--refresh` |
| `Search` | ask in plain text "Type keywords (title, author, Jira, repo) — or `clear`:" and wait, then rerun with `--q "<text>"` |
| Other (free text) | the same as the Other answer of step 1 |
| `Review selected PRs` | go to step 3 |

If nothing was picked at review time, say so in one line and stop.

## 3. Pick

```bash
~/work/chip/bin/chip pick "<label1>,<label2>,…"
```

On exit 2, show the error and re-ask. On exit 0 the output is a JSON array of `{index, label, repo, number, title, url}` in list order.

## 4. Review loop — one PR at a time

For item i of n:

1. Print `[i/n] <label> <title>`.
2. Run `~/work/chip/bin/chip repo <repo>` to get the local path.
   - On exit 2, ask with AskUserQuestion "No local clone of <repo>. Clone into <work_root>/.chip-repos/?" (Clone / Skip this PR). On Clone, run `~/work/chip/bin/chip repo <repo> --clone`. If the user chooses Skip or the clone fails, tell the user and skip to the next PR.
3. Invoke the `my-review-skill` skill with args: `<url> — local clone: <path>. The shell cwd resets between commands, so run every git/gh command as \`cd <path> && …\`.`
4. After the review report, if there is a next PR, ask with AskUserQuestion "Continue with <label>?" (Continue / Stop) and stop on Stop.

At the end, list which PRs were reviewed and which were skipped.

## Rules

- Never review a PR the user did not pick.
- Do not run reviews in parallel.
- Do not `git checkout`/`stash` in the user's clones; the review skill already reads refs with `git show`.
