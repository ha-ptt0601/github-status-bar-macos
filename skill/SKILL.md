---
name: chip
description: Use when the user runs /chip or asks which PRs are waiting for their review ("PR nào chờ review", "list PR cần review", "inbox review") and wants to pick some to review with /my-review-skill.
---

# chip — PR review inbox

`~/work/chip/bin/chip` does all the data work. You only pass its output to AskUserQuestion, collect the picks, and run the review loop. Never build, re-sort or filter the PR options yourself, and never print the PR list as a table.

## 1. Menu — pick PRs with AskUserQuestion

```bash
~/work/chip/bin/chip menu          # page 1, fetches from GitHub; add --all if the user asks for approved/draft PRs too
~/work/chip/bin/chip menu --page N # page N from the same fetch (no GitHub call)
```

Output is JSON: `{page, pages, total, hidden: {approved, draft}, questions: [...]}`.

- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- `total == 0`: say "Inbox zero 🎉" plus the hidden counts, and stop.
- Otherwise, before the first page, print one line: `<total> PR đang chờ bạn (ẩn <approved> đã approve, <draft> draft)`. Then call **AskUserQuestion with `questions` exactly as given**, without adding, removing or rewording anything.

After each page:
- Collect the selected labels from every `multiSelect` question and ignore `Không chọn`. An "Other" answer counts as labels or numbers typed by the user.
- If the nav question ("Tiếp theo?") was answered `Xem trang tiếp`, run `chip menu --page <page+1>` and ask again. Keep the labels you already collected.
- Otherwise (`Review các PR đã chọn`, or the last page), go to step 2.
- If nothing was picked on any page, say so in one line and stop.

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
