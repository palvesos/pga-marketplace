# Data Sources Reference — building-sprint-review

Detailed commands, field IDs, and JQL patterns for the
`building-sprint-review` skill. SKILL.md links here from Steps 1-5.

## Jira — sprint field

### Custom field IDs (OutSystems Atlassian Cloud)

| Field ID | Meaning |
|---|---|
| `customfield_10004` | Story Points |
| `customfield_10010` | **Sprint** (primary on OutSystems Jira Cloud) |
| `customfield_12600` | Dev info (PR linkage) |

If `customfield_10010` is missing on your project, also try `.fields.sprint`
or grep for the schema-name `com.atlassian.greenhopper.service.sprint.Sprint`
in the raw JSON.

### Sprint blob shape

The Sprint custom field is an array (a ticket can belong to multiple
sprints across its lifetime). Each entry:

```json
{
  "id": 12345,
  "name": "RDUCH Sprint 24",
  "state": "active",        // "active" | "closed" | "future"
  "startDate": "2024-05-06T08:00:00.000Z",
  "endDate":   "2024-05-19T17:00:00.000Z",
  "completeDate": null,     // populated when state == "closed"
  "goal": "Ship the LT→ODC connectivity MVP behind feature flag.",
  "boardId": 4321
}
```

For an active ticket, the **current** sprint is the entry with the latest
`startDate` (or `state == "active"` if exactly one is active). Don't
assume index 0.

## JQL patterns

```
# All tickets in a sprint, by name
sprint = "RDUCH Sprint 24"

# By numeric sprint ID
sprint = 12345

# Active sprints for a project (multiple boards may overlap — confirm with user)
sprint in openSprints() AND project = RDUCH

# Most recently closed sprint of a project
sprint in closedSprints() AND project = RDUCH ORDER BY endDate DESC

# Future sprints (next-sprint preview)
sprint in futureSprints() AND project = RDUCH

# Done items only (for velocity history)
sprint in closedSprints() AND project = RDUCH AND status = Done
```

### Useful fields to request

```
key,summary,status,assignee,issuetype,priority,labels,
customfield_10004,                  # Story Points
customfield_10010,                  # Sprint
customfield_12600,                  # Dev info / PRs
resolutiondate,
created
```

## Sprint changelog — detecting mid-sprint scope changes

`acli jira workitem view <KEY> --fields '*all' --expand changelog --json`

Inside the JSON:

```
.changelog.histories[].items[]
  where .field == "Sprint"
```

Each entry has `from` / `fromString` (previous sprint id/name) and
`to` / `toString` (new sprint id/name). Combined with `.changelog.histories[].created`
(the timestamp), you can determine:

- **Added mid-sprint** — `toString` contains the current sprint name AND
  `created > sprint.startDate`
- **Removed mid-sprint** — `fromString` contains the current sprint name
  AND `toString` does not (and `created < sprint.endDate`)

If a ticket has no Sprint changelog entry, it was in the sprint from
the start.

## Average velocity — methodology

1. Run the closed-sprints-Done JQL above.
2. Each ticket has a Sprint field that lists every sprint it touched.
3. Group SP by sprint name (the sprint where it was Done — usually the
   last sprint in its Sprint array with `state == "closed"`).
4. Take the 3 most recently closed sprints by `endDate`.
5. Average their SP totals.

**Edge cases:**

- A ticket marked Done in a sprint but moved out before close → exclude
  from that sprint's velocity (it didn't contribute to that sprint's
  delivery)
- A ticket carried across multiple sprints → count its SP only in the
  sprint where it transitioned to Done (use changelog)
- Fewer than 3 closed sprints exist → report what you have, label it
  as low-confidence

## GitHub PR linkage

Same as `building-initiative-dashboard` — two queries (open + closed) per
Done ticket, concatenate:

```bash
gh search prs "<KEY>" --limit 5 --json url,title,state,repository,isDraft
gh search prs "<KEY>" --limit 5 --state closed \
  --json url,title,state,repository,isDraft
```

The PR title convention `<KEY>: ...` makes this reliable across OutSystems
repos.

## Confluence — team context

```bash
koda tool confluence get --page-id <PAGE_ID>
```

### Known team pages

| Team | Confluence page ID | URL |
|---|---|---|
| Unification Charlie | `5852397579` | https://outsystemsrd.atlassian.net/wiki/spaces/RDO11PC/pages/5852397579/Unification+Charlie+Team |

If the user names a different team, ask for the page ID — don't guess.

Use the team page to populate:

- Team display name (sometimes differs from the project key)
- Working agreements / sprint cadence (cite only if asked)
- Team roster — useful for matching ticket assignee `email/displayName` to
  team-member friendly names on the demo slides

## Slack — team channel

| Team | Channel | URL |
|---|---|---|
| Unification Charlie | `#unification-charlie` | https://outsystems.enterprise.slack.com/archives/C0ABRM13LLS |

**The skill does NOT post to Slack.** It includes the channel URL on the
final deck slide and in the report footer so the audience knows where
follow-up discussion happens. The user shares the artifacts themselves.

## Auth troubleshooting

| Tool | Auth check | Fix |
|---|---|---|
| `acli` | `acli jira auth status` | `acli jira auth login` |
| `gh` | `gh auth status` | `gh auth login` |
| `koda confluence` | Errors mention missing token | Re-auth via `koda` |

If a tool isn't authenticated, **skip its data source** and continue with
what you have. Note the gap in the report footer ("Confluence team page
not queried — auth missing").
