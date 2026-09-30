---
name: chip
description: Use when the user runs /chip or asks which PRs are waiting for their review ("PR nào chờ review", "list PR cần review", "inbox review") and wants to pick some to review with /my-review-skill.
---

# chip — PR review inbox

`~/work/chip/bin/chip` does all the data work. You only show its output, ask the user, and run the review loop. Never re-sort, filter or re-render the table yourself.

## 1. List

```bash
~/work/chip/bin/chip list          # add --all if the user asks for approved/draft PRs too
```

- Exit 0: paste stdout **verbatim** in your reply (it is a markdown table plus an optional "Ẩn: …" footer). Then ask: "Chọn PR để review (vd `1,3`, `2-4`, `all`):" and wait.
- Exit 1: show stderr as-is (it includes the `! gh auth login` hint when relevant) and stop.
- "Inbox zero 🎉": show it and stop.

## 2. Pick

```bash
~/work/chip/bin/chip pick "<user text>"
```

Exit 2 → show the error and ask again. Exit 0 → a JSON array of `{index, repo, number, title, url}` in table order.

## 3. Review loop — one PR at a time

For item i of n:

1. Print `[i/n] <repo>#<number> <title>`.
2. `~/work/chip/bin/chip repo <repo>` → the local path.
   - Exit 2: ask "Chưa có clone local của <repo>. Clone vào ~/work/.chip-repos/?" Yes → `~/work/chip/bin/chip repo <repo> --clone`. No, or clone fails → tell the user and skip to the next PR.
3. Invoke the `my-review-skill` skill with args: `<url> — local clone: <path>. The shell cwd resets between commands, so run every git/gh command as \`cd <path> && …\`.`
4. After the review report, if there is a next PR ask "Tiếp PR kế (<repo>#<number>)?" and stop on no.

At the end, list which PRs were reviewed and which were skipped.

## Rules

- Never review a PR the user did not pick.
- Do not run reviews in parallel.
- Do not `git checkout`/`stash` in the user's clones; the review skill already reads refs with `git show`.
