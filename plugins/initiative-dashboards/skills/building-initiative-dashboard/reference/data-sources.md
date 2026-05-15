# Data Sources Reference

Detailed commands and field IDs for each data source used by the
`building-initiative-dashboard` skill. SKILL.md links here from Step 1-3.

## Jira

### Useful custom field IDs (OutSystems Atlassian Cloud)

| Field ID | Meaning |
|---|---|
| `customfield_10004` | Story Points |
| `customfield_10007` | Epic Link / Parent |
| `customfield_10008` | Epic Name |
| `customfield_10009` | Epic Status |
| `customfield_12600` | Dev info (PR linkage — GitHub, Bitbucket) |

### Parsing `customfield_12600` (Dev info)

This field is a string blob. Use regex:

```
state=(OPEN|MERGED|CLOSED|DECLINED)
stateCount=(\d+)
"byInstanceType":{"GitHub":{"count":1,"name":"GitHub"}}
```

The PR URL is **not** in this field — search GitHub via `gh search prs "<KEY>"`
to recover it.

### Useful JQL patterns

```
# Epic children
"Epic Link" = RDUCH-169 OR parent = RDUCH-169

# Linked issues (cross-team)
issue in linkedIssues(RDUCH-169)

# All initiative tickets (loose match)
text ~ "PU-M4.13" OR summary ~ "LT Connectivity"

# Active items only
status not in (Done, Closed, Cancelled)
```

### Status taxonomy (typical)

Common statuses across OutSystems R&D projects:

`Definition`, `To Do`, `In Progress`, `In Peer Review`, `In Testing`, `Done`

Order for sorting / chart axes: Definition → To Do → In Progress →
In Peer Review → In Testing → Done.

### Pagination & limits

`acli jira workitem search` defaults to a reasonable page; if `--limit`
needed, use `--limit 100`.

## GitHub

### Finding PRs linked to a Jira key

`gh search prs --state` only accepts `open` or `closed` — there is no
`all`. Use two queries when you need both:

```bash
# Open PRs (default)
gh search prs "<KEY>" --limit 5 \
  --json url,title,state,repository,isDraft

# Closed / merged PRs
gh search prs "<KEY>" --limit 5 --state closed \
  --json url,title,state,repository,isDraft
```

Searches title and body. The PR title convention `<KEY>: ...` makes this
reliable across OutSystems repos.

### Getting PR details

```bash
gh pr view <NUMBER> --repo <OWNER>/<REPO> --json \
  url,title,state,isDraft,additions,deletions,reviewDecision,statusCheckRollup,mergeable,createdAt,updatedAt
```

Useful for surfacing CI status (`statusCheckRollup[].conclusion`) and review
state (`reviewDecision` = `APPROVED` / `REVIEW_REQUIRED` / `CHANGES_REQUESTED`).

### Closed-but-merged PRs

`gh search prs "<KEY>"` without `--state` defaults to `open`. Run a second
query with `--state closed` to include merged PRs.

You can also filter by merged state directly:

```bash
gh search prs "<KEY>" --merged --limit 5 \
  --json url,title,state,repository,mergedAt
```

## Productboard

```bash
# Custom field definitions (one-time discovery)
npx -y github:OutSystems/prodeng-productboard list_custom_fields --args '{}'

# Feedback for a feature
npx -y github:OutSystems/prodeng-productboard list_feedback \
  --args '{"featureId":"<UUID>"}'

# Jira-linked feedback for a ticket
npx -y github:OutSystems/prodeng-productboard list_jira_feedback \
  --args '{"issueKey":"<KEY>"}'
```

If `productboard.auth.token` is not configured, the CLI errors clearly.
Skip the section in that case.

## Confluence (via koda tool)

```bash
# Fetch a page by ID
koda tool confluence get --page-id <PAGE_ID>

# Search for related pages
koda tool confluence search "<query>"
```

The design spec and UX page IDs are usually linked from the Jira epic
description or from a `session-notes.md` in the project folder. Extract
them via regex from the epic description or context file.

## Google Sheets — Initiatives Roadmap

```bash
# Get spreadsheet metadata (list of tabs / sheet IDs)
npx -y github:OutSystems/prodeng-drive-cli sheets get <SPREADSHEET_ID>

# Read a range (rows 1-300 across all columns A:AB)
npx -y github:OutSystems/prodeng-drive-cli sheets read <SPREADSHEET_ID> 'A1:AB300'

# Read just the headers
npx -y github:OutSystems/prodeng-drive-cli sheets read <SPREADSHEET_ID> '1:1'
```

### Column discovery (fuzzy match)

The roadmap sheet has ~28 columns (A–AB). Don't hardcode column names —
fuzzy-match the headers at runtime:

| Concept | Header patterns to match (case-insensitive) |
|---|---|
| Initiative identifier | `Initiative`, `ID`, `Code`, `Jira`, `Epic`, `PB ID`, `Productboard` |
| Priority | `Priority`, `Rank`, `VS Rank`, `Order` |
| Quarter / timing | `Quarter`, `Q`, `Target`, `ETA`, `Due`, `Date` |
| Value Stream | `Value Stream`, `VS`, `Stream` |
| Status | `Status`, `Stage`, `State` |
| Owner | `Owner`, `EM`, `PM`, `Lead`, `Assignee` |

Once headers are identified, find the initiative's row by matching the
identifier column against the user-provided Jira key, Productboard UUID,
or initiative code (e.g. `PU-M4.13.1`).

### Roadmap sheet (OutSystems)

The known sheet ID is `14tIZS6lMahe0YKUQF-EYC9m7Wr8VRkSyXfOIbLP6UYo`.

Treat this as a default — if the user provides a different sheet ID or
URL, use theirs.

## Auth troubleshooting

| Tool | Auth check | Fix |
|---|---|---|
| `acli` | `acli jira auth status` | `acli jira auth login` |
| `gh` | `gh auth status` | `gh auth login` |
| `prodeng-productboard` | Errors mention missing token | Set `productboard.auth.token` in `~/.config/outsystems-cli/config.json` |
| `prodeng-drive-cli` | `Credentials file not found` | `npx -y github:OutSystems/prodeng-drive-cli auth login` |

If a tool isn't authenticated, **skip its data source** and continue.
Note the gap in the dashboard's "Sources queried" footer.
