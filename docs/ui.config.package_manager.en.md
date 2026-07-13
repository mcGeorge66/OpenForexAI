[Back to UI Handbook](ui.en.md) › [Config](ui.config.en.md)

# Package Manager

`Package Manager` enables selective export and import of configuration packages. This allows parts of the runtime configuration to be transferred between installations, backed up, or applied to new environments.

---

## Workflow

The Package Manager works in three steps: **Export → Validate → Import**.

---

## Export Section

### Areas to export

Checkboxes for each supported configuration area:

| Checkbox | Content |
|---|---|
| **Include Agents** | Agent configurations |
| **Include Snapshot Profiles** | Snapshot profiles |
| **Include Decision Prompt Profiles** | Decision prompt profiles |
| **Include Bridge Tools** | Bridge tool definitions |
| **Include Event Routing** | Event routing rules |
| **Include System Config** | Global `system.json5` (default: disabled) |
| **Strict agent dependencies** | Fails if referenced LLM/broker modules are not present |

### Agent selection

List of all agents from the current configuration. Each agent has a checkbox. Only selected agents are exported.

| Button | Function |
|---|---|
| **Select all** | Select all agents |
| **Clear** | Deselect all agents |

### Export Selected Areas

Downloads a `.json5` package with the selected areas and a timestamp in the filename. Disabled if no areas are selected.

---

## Package Content Section

Where the package to be imported is entered.

| Element | Function |
|---|---|
| **Drag & Drop Zone** | Drag in a `.json5`, `.json`, or `.txt` file |
| **Load package file** | Opens file picker |
| **Textarea** | Paste or edit package JSON5 directly |

---

## Mapping & Import Section

### Mapping Fields

Allow renaming IDs during import — necessary when the target installation uses different module or agent names.

| Field | Format | Function |
|---|---|---|
| **Agent ID Prefix** | Text (e.g. `DEMO-`) | Prepended to all imported agent IDs |
| **Broker Mapping** | One per line: `old=new` | Renames broker module names |
| **LLM Mapping** | One per line: `old=new` | Renames LLM module names |
| **Agent ID Mapping** | One per line: `old=new` | Renames specific agent IDs |

**Example Broker Mapping:**
```
broker_oanda=broker_live
broker_demo=broker_paper
```

### Import Options

| Checkbox | Function |
|---|---|
| **Replace existing agents** | Overwrites agents with the same ID (default: disabled — duplicate IDs fail) |
| **Import agents** | Import agent configurations |
| **Import snapshot profiles** | Import snapshot profiles |
| **Import decision prompt profiles** | Import decision prompt profiles |
| **Import bridge tools** | Import bridge tools |
| **Import event routing** | Import routing rules |
| **Import system config** | Import `system.json5` (default: disabled) |

### Validate

Validates the package without applying it. Shows all errors and warnings in the validation table. Recommended before every import.

### Import

Applies the package with all active mappings and options. Disabled if no package is present.

---

## Validation Table

Appears after Validate or a failed import. Shows:

| Column | Content |
|---|---|
| **Level** | `error` (blocks import) or `warning` (import possible) |
| **Path** | Path to the affected configuration element |
| **Message** | Description of the problem |

---

## Typical Workflow: Export

1. Select areas (checkboxes)
2. Select agents
3. Click **Export Selected Areas** → file is downloaded

## Typical Workflow: Import

1. Drag or load the package file into the drop zone
2. Fill in mapping fields if IDs need to be adjusted
3. Review import options
4. Click **Validate** and check the validation table
5. Correct errors in the package or mappings
6. Click **Import**
