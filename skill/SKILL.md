---
name: chip
description: Use when the user runs /chip or asks which PRs are waiting for their review ("PR nào chờ review", "list PR cần review", "inbox review") and wants to pick some to review with /my-review-skill.
---

# chip — PR review inbox

`~/work/chip/bin/chip` does all the data work. You only pass its output to AskUserQuestion, collect the picks, and run the review loop. Never build, re-sort or filter the PR options yourself, and never print the PR list as a table.

## 0. Default: open the search picker in a new terminal window

Unless the args contain `menu` (for example `/chip menu` or `/chip menu newsletter`), run:

```bash
~/work/chip/bin/chip open
```

- **Exit 0:** reply with one line, "Đã mở `chip` trong cửa sổ Terminal mới: gõ để tìm, Tab tick, Enter review (review chạy trong cửa sổ đó).", and **stop**. Do not load the menu, and do not review anything in this session.
- **Exit 1 or 2:** show stderr, then continue with step 1 (the in-chat menu).

## 1. Menu — pick PRs with AskUserQuestion (`/chip menu`, or when `chip open` failed)

```bash
~/work/chip/bin/chip menu [--q "<words>"] [--repo a,b]          # fetch from GitHub (first call only); add --all for approved/draft too
~/work/chip/bin/chip menu --cached [--page N] [--q …] [--repo …] # every later call: same fetch, no GitHub call
~/work/chip/bin/chip repos                                        # repo-filter questions, from the same fetch
```

If `/chip menu` was given more args (e.g. `/chip menu newsletter`), pass the words after `menu` as `--q "<words>"` on the first call. The search matches title, author, Jira key, repo and base, and every word must match.

The output is JSON: `{page, pages, total, filter, hidden: {approved, draft}, questions: [...]}`.

- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- `total == 0` with no filter: say "Inbox zero 🎉" plus the hidden counts, and stop.
- `total == 0` with a filter: say "Không có PR khớp `<filter>`", then ask for a new keyword, or offer to clear the filter.
- Otherwise, before the first page, print one line: `<total> PR đang chờ bạn (ẩn <approved> đã approve, <draft> draft)`. Add `· lọc: <filter>` when there is a filter. Then call **AskUserQuestion with `questions` exactly as given**, without adding, removing or rewording anything.

Keep the current filter state (`q`, `repo`) and **every label picked so far** across pages and filter changes. After each page, collect the selected labels from every `multiSelect` question, ignoring `Không chọn`. Then act on the nav question ("Tiếp theo?"):

| Nav answer | Do |
|---|---|
| `Xem trang tiếp` | `chip menu --cached --page <page+1>`, with the same `--q`/`--repo` |
| `Lọc theo repo` | `chip repos` → AskUserQuestion with its `questions` as given → `chip menu --cached --repo <picked names joined by ,>` (keep `--q`). If nothing is picked, or only `Không chọn`, clear the repo filter. |
| `Tìm kiếm` | Ask in plain text "Gõ từ khoá (title, author, Jira, repo) — hoặc `bỏ lọc`:" and wait. Then run `chip menu --cached --q "<text>"` (keep `--repo`). On `bỏ lọc`, drop both filters. |
| Other (free text) | Treat as a search keyword, the same as `Tìm kiếm` with that text. `bỏ lọc` clears the filters. |
| `Review các PR đã chọn` | Go to step 2. |

Before each re-ask after the first, print one line with the labels picked so far. If nothing was picked when the user chooses review, say so in one line and stop.

## 2. Pick

```bash
~/work/chip/bin/chip pick "<label1>,<label2>,…"
```

On exit 2, show the error and re-ask the page that holds the bad label. On exit 0 the output is a JSON array of `{index, label, repo, number, title, url}` in list order.

## 3. Review loop — one PR at a time

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
