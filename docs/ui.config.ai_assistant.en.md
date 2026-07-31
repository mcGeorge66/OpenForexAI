[Back to Config](ui.config.en.md)

# AI-Assistant — Handbook

Almost every Config editor in OpenForexAI has an **AI Assistant** button in the top right, opening a chat window where you can ask questions about the configuration you're currently editing — e.g. "why does this tool_block return no data" or "how do I build a session filter for the London session." Each of these assistants is driven by its own **context file** — a Markdown file that tells the LLM what this editor is for, what fields exist, and what to watch out for. The **AI-Assistant** page is the editor for exactly these context files.

You typically don't come here to configure something yourself, but to make the assistant in *another* editor **better** — e.g. after it answered a question incorrectly or incompletely.

Stored under `config/llm_contexts/*.md`.

---

## 1. How the Embedded Assistant Works

When you click **AI Assistant** in a config editor (e.g. Snapshot Config, Decision Prompt, Bridge Tools, Chartshot Config, Entity Config), a chat window opens. Every message is sent to the LLM together with three things:

1. The **context file content** — the actual "knowledge" this assistant has about that particular editor.
2. The **current configuration state** (`context_data`) — a JSON dump of whatever is currently in the editor, so questions like "why is this block failing" refer to the real, current values.
3. The chat's **conversation history** so far.

The chat history persists per context file even if the window is closed and reopened — it's only lost on a page reload. **Clear** clears it explicitly.

**Warning — security:** the current configuration state (item 2) is sent **verbatim** to the LLM. If a config editor contains sensitive values (e.g. plaintext API keys instead of `${ENV_VAR}` placeholders), those end up in the prompt sent to whatever LLM provider is configured. Always reference sensitive values via environment variables rather than entering them directly — that's the recommended practice for module configs anyway, but it matters especially here because the content is actively transmitted to an external service.

---

## 2. Which Context Files Exist

| File | Used in |
|---|---|
| `agent_config_assistant.md` | Agent Config |
| `entity_config_assistant.md` | Entity Config, Helper Config |
| `snapshot_config_assistant.md` | Snapshot Config |
| `decision_prompt_assistant.md` | Decision Prompt |
| `bridge_tools_assistant.md` | Bridge Tools |
| `event_routing_assistant.md` | Event Routing |
| `chartshot_config_assistant.md` | Chartshot Config |
| `script_snapshot_transform_context.md` | Transform-script editor (Snapshot Config, Prompt Workbench) |
| `script_snapshot_calculation_context.md` | Calculation-block script editor |
| `script_snapshot_assembly_context.md` | Assembly-transform script editor |
| `script_decision_prompt_context.md` | Decision-prompt script editor |
| `script_decision_selector_context.md` | Decision-selector script editor |
| `script_ec_context.md` | Event Composer script editor |

New `.md` files placed in `config/llm_contexts/` automatically appear in this page's dropdown.

---

## 3. Editor UI

| Element | Function |
|---------|---------|
| **File selector dropdown** | Chooses which context file to edit. |
| **Edit / Split / Preview** | Plain editor, split view, or rendered preview only. |
| **Save** | Writes the file back. Only enabled with unsaved changes. |

**Recommendation:** always use `Split` while writing — Markdown tables and code blocks can look subtly different in raw text than they do once rendered, and it's exactly that rendered structure that makes them easy for an LLM to parse.

---

## 4. Writing a Good Context File

Since the content is passed directly to the LLM as background knowledge, the same rules apply here as for system prompts:

- **Be concrete:** what fields exist, what they do, what values are typical/valid.
- **Name common mistakes:** if users regularly ask the same question or make the same mistake, the answer/explanation belongs in the context file.
- **Keep it short:** the content is resent on every chat message — unnecessarily long files slow down and increase the cost of every answer without adding value.
- **Include examples:** a short example of a typical config entry often helps the LLM more than an abstract description.

**Example — a weak entry vs. a better one** (excerpt from a hypothetical `bridge_tools_assistant.md`):

Weak (too abstract, no example):
> "The `allowed_tools` field controls which tools are exposed."

Better (concrete, with an example and a warning):
> "`allowed_tools` is a list of tool names this bridge entry exposes, e.g. `[\"get_candles\", \"get_account_status\"]`. An empty array blocks all tools — this is the most common cause of a bridge call failing with 'tool not allowed' even though the entry otherwise looks correct."

The second entry directly answers the question a user is likely to ask, instead of just naming the field.

---

## 5. Typical Workflow: Improving an Assistant After a Wrong Answer

1. In the relevant config editor (e.g. Bridge Tools), you ask the AI Assistant a question and the answer is wrong or too vague.
2. Switch to the **AI-Assistant** page and pick the matching context file from the dropdown (e.g. `bridge_tools_assistant.md`).
3. Switch to `Split` mode.
4. Add exactly the point the assistant didn't know — ideally in the example style from Section 4 (a concrete field, concrete behavior, and any known failure cause).
5. Click `Save` — takes effect immediately, no restart.
6. Go back to the original editor and ask the same question again to confirm the improvement.

**Tip:** if several users share the same assistant, it's worth systematically capturing recurring questions in the context file instead of re-answering them in chat every time — the context file effectively becomes a living FAQ for that editor.
