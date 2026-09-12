# Tool check from routine host session

- **UTC time:** 2026-09-12T18:41:00Z
- **Working directory:** /home/user/hellomass
- **Repository present:** yes, on branch `claude/nice-pasteur-omkzao` (tracking `origin/claude/nice-pasteur-omkzao`)

## `git remote -v`

```
origin	https://github.com/santoshdotai/hellomass (fetch)
origin	https://github.com/santoshdotai/hellomass (push)
```

## Tool availability

| Tool | Present | Notes |
| --- | --- | --- |
| `mcp__Gmail__*` | yes (under a UUID prefix) | No tool is literally named `mcp__Gmail__*`. A Gmail MCP server is connected as `mcp__4faa7b93-5432-4cd5-bc1c-342136c7c652__*` (server description: "MCP server provided by Gmail API") with `send_message`, `create_draft`, `search_threads`, `get_thread`, `reply`, `forward`, label tools, etc. |
| `mcp__Google_Calendar__*` | partial (under a UUID prefix) | No tool is literally named `mcp__Google_Calendar__*`. A calendar MCP server is connected as `mcp__9dd9257d-74e2-48bb-a01c-d78d6f40f2f0__*` with `list_calendars`, `list_events`, `create_event`, `update_event`, `delete_event`, `search_events`, `respond_to_event`, `suggest_time`. The server does not self-identify as Google Calendar. Calendly (`mcp__03213990-...`) is also connected. |
| `Artifact` | yes | Loaded in the primary tool list. |
| `WebSearch` | yes | Deferred tool; loadable via ToolSearch and callable. |

## Model

- Configured model id: `claude-fable-5-1`
- Fallback chain: `claude-fable-5[1m]`, `claude-opus-5[1m]`, `claude-opus-4-8[1m]`
- The model actually serving a given turn may differ from the configured id.
