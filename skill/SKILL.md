---
name: chip
description: Use when the user runs /chip or asks which PRs are waiting for their review ("PR nào chờ review", "list PR cần review", "inbox review") and wants to pick some to review with /my-review-skill.
---

# chip — PR review inbox

`~/work/chip/bin/chip` does all the data work. You only pass its JSON to AskUserQuestion, collect the picks, and run the review loop. Never build, re-sort or filter options yourself, never reword them, and never print the PR list as a table.

Args:
- `/chip`: the in-chat flow below.
- `/chip <words>`: skip step 1 and start step 2 with `--q "<words>"` (the search matches title, author, Jira, repo and base).
- `/chip terminal`: run `~/work/chip/bin/chip open`. That opens the fzf picker in a new Terminal window. Reply with its stdout (or stderr on failure) and stop.

## 1. Choose the project (one keystroke)

```bash
~/work/chip/bin/chip repos --refresh     # fetches from GitHub (~5s), or reuses a fetch < 3 min old; add --force if the user asks to reload
                                         # later in the flow: `chip repos` (no --refresh) reuses the same fetch
```

Output: `{total, hidden: {approved, draft}, updated, questions}`. `questions` holds ONE single-select question: `Tất cả` plus the 3 busiest repos. The other repos are listed in the question text for typing.

- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- `total == 0`: "Inbox zero 🎉" plus the hidden counts, then stop.
- Otherwise, print one line, `<total> PR đang chờ bạn (ẩn <approved> đã approve, <draft> draft · cập nhật <updated>)`. Then call **AskUserQuestion with `questions` exactly as given**.
- Answer `Tất cả`: no filter. A repo label: `--repo <label>`. Other text: if it equals or contains a repo name from the question, use `--repo <that name>`; otherwise use `--q "<text>"`.

## 2. Tick PRs

```bash
~/work/chip/bin/chip menu --cached [--repo a] [--q "<words>"] [--page N]
```

(For `/chip <words>`, where step 1 was skipped, the first call is `chip menu --q "<words>"` without `--cached`. It fetches from GitHub.)

The output is `{page, pages, total, filter, hidden, questions}`. Call **AskUserQuestion with `questions` exactly as given**. If `total == 0`, say "Không có PR khớp `<filter>`" and go back to step 1.

When the result has **16 PRs or fewer**, `questions` contains only multi-select PR questions and no nav question: the user ticks and submits once. Collect the ticked labels, ignoring `Không chọn`, and go straight to step 3. If an Other answer holds text instead, treat that text like the Other answer of step 1 (switch project or search), keep the labels ticked so far, and rerun this step.

When the result has **more than 16 PRs**, there are pages of 12 plus a nav question "Tiếp theo?". Keep the filter state and **every label picked so far** across pages:

| Nav answer | Do |
|---|---|
| `Xem trang tiếp` | the same command with `--page <page+1>` |
| `Đổi project` | step 1 again, using `chip repos` without `--refresh` |
| `Tìm kiếm` | ask in plain text "Gõ từ khoá (title, author, Jira, repo) — hoặc `bỏ lọc`:" and wait, then rerun with `--q "<text>"` |
| Other (free text) | the same as the Other answer of step 1 |
| `Review các PR đã chọn` | go to step 3 |

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
   - On exit 2, ask with AskUserQuestion "Chưa có clone local của <repo>. Clone vào ~/work/.chip-repos/?" (Clone / Bỏ qua PR này). On Clone, run `~/work/chip/bin/chip repo <repo> --clone`. If the user chooses Bỏ qua or the clone fails, tell the user and skip to the next PR.
3. Invoke the `my-review-skill` skill with args: `<url> — local clone: <path>. The shell cwd resets between commands, so run every git/gh command as \`cd <path> && …\`.`
4. After the review report, if there is a next PR, ask with AskUserQuestion "Tiếp PR kế (<label>)?" (Tiếp / Dừng) and stop on Dừng.

At the end, list which PRs were reviewed and which were skipped.

## Rules

- Never review a PR the user did not pick.
- Do not run reviews in parallel.
- Do not `git checkout`/`stash` in the user's clones; the review skill already reads refs with `git show`.
