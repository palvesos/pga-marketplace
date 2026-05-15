# pga-marketplace

Paulo Alves' personal Claude Code marketplace.

## Plugins

| Plugin | Description |
|---|---|
| [initiative-dashboards](plugins/initiative-dashboards) | EM/PM tooling — turn a Jira epic key into a self-contained executive progress dashboard (Jira tree + GitHub PRs + Productboard + Confluence + roadmap sheet). |

## Installing

In Claude Code:

```
/plugin marketplace add palvesos/pga-marketplace
/plugin install initiative-dashboards@pga-marketplace
```

## Using

After install, the `building-initiative-dashboard` skill auto-activates on prompts like:

- *"build a dashboard for RDUCH-169"*
- *"create a progress dashboard for epic ABC-123"*
- *"executive report for initiative XYZ"*

See the plugin README for prerequisites (acli, gh, optional Productboard / Drive auth) and the data sources it pulls from.
