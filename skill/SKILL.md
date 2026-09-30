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

## 1. Choose the project

```bash
~/work/chip/bin/chip repos --refresh     # fetches from GitHub; later: `chip repos` (no --refresh) reuses the fetch
```

Output: `{total, hidden: {approved, draft}, questions}`.

- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- `total == 0`: "Inbox zero 🎉" plus the hidden counts, then stop.
- Otherwise, print one line, `<total> PR đang chờ bạn (ẩn <approved> đã approve, <draft> draft)`. Then call **AskUserQuestion with `questions` exactly as given**.
- If `Tất cả` or nothing is picked, use no repo filter. Otherwise use `--repo <picked labels joined by ,>`.

## 2. Tick PRs, page by page

```bash
~/work/chip/bin/chip menu --cached [--repo a,b] [--q "<words>"] [--page N]
```

(For `/chip <words>`, where step 1 was skipped, the first call is `chip menu --q "<words>"` without `--cached`. It fetches from GitHub.)

The output is `{page, pages, total, filter, hidden, questions}`. Call **AskUserQuestion with `questions` exactly as given**. If `total == 0`, say "Không có PR khớp `<filter>`" and go back to step 1.

Keep the filter state (`repo`, `q`) and **every label picked so far** across pages, project changes and searches. After each page, collect the labels from every `multiSelect` question, ignoring `Không chọn`. Then act on the nav answer ("Tiếp theo?"):

| Nav answer | Do |
|---|---|
| `Xem trang tiếp` | the same command with `--page <page+1>` |
| `Đổi project` | step 1 again, using `chip repos` without `--refresh`. Keep `--q`. |
| `Tìm kiếm` | ask in plain text "Gõ từ khoá (title, author, Jira, repo) — hoặc `bỏ lọc`:" and wait, then rerun with `--q "<text>"`. `bỏ lọc` clears `q`. |
| Other (free text) | the same as `Tìm kiếm` with that text |
| `Review các PR đã chọn` | go to step 3 |

Before each re-ask after the first, print one line with the labels picked so far. If nothing was picked at review time, say so in one line and stop.

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
