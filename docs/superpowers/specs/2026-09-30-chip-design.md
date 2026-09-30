# chip: PR review inbox

Date: 2026-09-30
Status: approved (design)

## Goal

Every day there are many PRs waiting for the user (GitHub login `ha-ptt0601`) to review. `/chip` in Claude Code shows the PRs that are actually waiting on the user as a table. The user picks some of them, and chip runs the existing skill `/my-review-skill` on each one in turn.

## Non-goals

- No scheduled or recurring runs, and no notifications (can be added later).
- No parallel reviews.
- No changes to `/my-review-skill`.

## Architecture

```
/chip (skill, SKILL.md)
  ├─ runs  bin/chip-list --json      → deterministic data: PR rows + hidden counts
  ├─ renders table, asks user to pick (free text: "1,3", "2-4", "all")
  └─ for each picked PR, one at a time:
       bin/chip-repo owner/repo      → local clone path (discover / cache / clone)
       invoke /my-review-skill <PR url>  (from that repo dir)
       ask "Tiếp PR kế?" before the next one
```

The two scripts are Python 3.9 with the stdlib only, and they call `gh`. The skill contains no data logic of its own. It only renders, asks and orchestrates.

### Files (`~/work/chip`)

| Path | Purpose |
|---|---|
| `chip/fetch.py` | Build and run the GraphQL searches through `gh api graphql`, merge and dedupe the results |
| `chip/model.py` | Pure functions: raw PR node → row (status, CI, size, stacked, Jira key, wait time), sorting, visibility |
| `chip/select.py` | Parse the user's selection string → list of row indexes |
| `chip/repos.py` | Find a local clone for `owner/repo`: cache, scan, clone |
| `bin/chip-list` | CLI: fetch → model → JSON on stdout (or a plain-text table with `--table`) |
| `bin/chip-repo` | CLI: `chip-repo owner/repo [--clone]` → prints the path, or exits 2 if no clone is found |
| `skill/SKILL.md` | The `/chip` skill; symlinked to `~/.claude/skills/chip` |
| `tests/` | `unittest` tests with fixture JSON, no network |

## Data source

Two GraphQL `search` queries (type ISSUE, first 100, with pagination):

1. `is:pr is:open review-requested:@me -author:@me`
2. `is:pr is:open reviewed-by:@me -author:@me`

The second query is required. When the user submits a review, GitHub removes them from the requested reviewers, so PRs that need a re-review would otherwise disappear. The results are merged and deduped by PR `id`.

Fields per PR: `number, title, url, isDraft, createdAt, author.login, repository.nameWithOwner, repository.defaultBranchRef.name, baseRefName, headRefName, headRefOid, additions, deletions, changedFiles, mergeable, reviewDecision, commits(last:1){commit{committedDate, statusCheckRollup{state}}}, latestReviews(first:20){author.login, state, submittedAt}, reviewRequests(first:20){requestedReviewer{... on User{login}}}`, plus `viewer.login`.

## Row model

**My status** is based on the viewer's entry in `latestReviews` and the last commit's `committedDate`:

| Condition | Status |
|---|---|
| No review by the viewer | `new` (mới) |
| Viewer review older than the last commit | `re-review` (cần re-review) |
| Viewer's latest review is `CHANGES_REQUESTED`, with no newer commit | `waiting-author` (chờ author) |
| Viewer's latest review is `APPROVED`, with no newer commit | `approved` (hidden) |
| Viewer's latest review is `COMMENTED` or `DISMISSED`, with no newer commit | `commented` (visible, treated like `waiting-author` when sorting) |

If the viewer has been explicitly re-requested (the viewer is in `reviewRequests`) and the status is not `new`, the status becomes `re-review`.

**Other columns**

- `wait`: time since `createdAt`, formatted as `45m`, `6h` or `9d`.
- `decision`: `APPROVED` / `CHANGES_REQ` / `REQUIRED` / `-`, followed by the ✓ and ✗ counts taken from `latestReviews`.
- `size`: `+additions/-deletions Nf`.
- `ci`: `SUCCESS` → ✓, `FAILURE` or `ERROR` → ✗, `PENDING` or `EXPECTED` → ⏳, none → `-`.
- `conflict`: shows `⚠` when `mergeable == CONFLICTING`.
- `base`: `baseRefName`, plus a `stacked` flag when it differs from the default branch.
- `jira`: first match of `[A-Z][A-Z0-9]+-\d+` in the title, then in `headRefName`; empty if none.

**Visibility.** `approved` rows and drafts are hidden by default. The JSON output includes `hidden: {approved: N, draft: M}`, and `--all` shows every row.

**Sort order.** `re-review`, then `new`, then `waiting-author`/`commented`. Within each group, the oldest `createdAt` comes first. Rows are numbered from 1 after sorting.

## Selection

The user types free text: `1,3,5`, `2-4`, `1,3-5`, or `all`. Whitespace is ignored. Out-of-range or malformed tokens raise an error that lists the bad token, and the skill asks again. Duplicates are removed and the displayed order is kept.

## Local repo resolution (`chip-repo`)

1. Look up the cache at `~/.cache/chip/repos.json` (`{"owner/repo": "/abs/path"}`). A cached entry is used only if the path still exists and its `origin` still matches.
2. Otherwise scan `~/work` up to 3 levels deep for `.git` directories, skipping `node_modules`, `vendor` and `.chip-repos` itself. Match the `origin` URL, normalizing ssh/https and a trailing `.git`. Every match found is written back to the cache.
3. Also check `~/work/.chip-repos/<repo>`.
4. If nothing is found, exit with code 2. The skill then asks the user and, on yes, runs `chip-repo owner/repo --clone`, which does `gh repo clone owner/repo ~/work/.chip-repos/<repo>` and prints the path.

## Review loop (skill)

For each selected row, in order:
- Print a one-line header: `[i/n] repo#PR title`.
- Resolve the repo path, `cd` into it, and invoke `/my-review-skill <url>`. The review skill's own rules, such as skipping PRs already approved or never checking out in the working tree, still apply.
- After its report, ask "Tiếp PR kế (repo#PR)?" and stop if the user says no.

## Error handling

- `gh` not authenticated: print the error and suggest `! gh auth login`.
- GraphQL errors or rate limit: print the message and exit 1. No automatic retry.
- Zero visible rows: print "Inbox zero 🎉" plus the hidden counts.
- Clone failure: show the gh error and skip that PR after telling the user.

## Testing

`python3 -m unittest discover tests` (Python 3.9 stdlib, since pytest is not installed):
- `model`: each status branch, the re-request override, CI mapping, stacked flag, Jira regex, wait formatting, sort order, visibility.
- `select`: valid forms, ranges, `all`, duplicates, errors.
- `repos`: remote URL normalization; scanning a temp directory tree with fake git repos (real `git init` plus `remote add`); cache invalidation.
- `fetch`: merge and dedupe of two fixture responses (the `gh` call is injected).
