# Plan: Kanonisches Message-Format von Anthropic auf OpenAI umstellen

## Problem

Das interne Gesprächsformat für Tool-Use-Konversationen (Conversation History) ist
derzeit **Anthropic-nativ**. Das bedeutet: alle anderen LLM-Provider (Azure, OpenAI,
LM Studio, Ollama, Grok, …) brauchen eine Konvertierung, obwohl OpenAI-Format der
klare Marktstandard ist (~80% der Provider sprechen es nativ).

Aktuell:
- `agent.py` baut History in Anthropic-Format → nur Anthropic braucht keine Konvertierung
- Azure hat `_sanitize_messages` als Workaround
- LM Studio, Ollama, OpenAI, Grok fehlt die Konvertierung komplett → würden bei Tool-Use crashen

Ziel:
- `agent.py` baut History in OpenAI-Format → alle OpenAI-kompatiblen Provider laufen direkt
- Nur Anthropic bekommt eine `_sanitize_messages` Funktion

---

## Format-Vergleich

### Assistant-Turn mit Tool-Call

**OpenAI (neu — intern kanonisch):**
```json
{
  "role": "assistant",
  "content": "Ich schaue nach offenen Positionen.",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "get_open_positions",
        "arguments": "{\"pair\": \"EURUSD\"}"
      }
    }
  ]
}
```

**Anthropic (wird nach Umstellung nur noch im Anthropic-Adapter erzeugt):**
```json
{
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Ich schaue nach offenen Positionen."},
    {"type": "tool_use", "id": "call_abc123", "name": "get_open_positions", "input": {"pair": "EURUSD"}}
  ]
}
```

### Tool-Result-Turn

**OpenAI (neu — ein Message pro Result):**
```json
{"role": "tool", "tool_call_id": "call_abc123", "content": "{\"count\": 0}"}
```

**Anthropic (alle Results in einer User-Message):**
```json
{
  "role": "user",
  "content": [
    {"type": "tool_result", "tool_use_id": "call_abc123", "content": "{\"count\": 0}"}
  ]
}
```

**Wichtig:** Mehrere Tool-Results = mehrere separate Messages in OpenAI, aber ein
einziger User-Block in Anthropic. Die Anthropic-Konvertierung muss das zusammenfassen.

---

## Dateien die geändert werden müssen

### 1. `openforexai/agents/agent.py`

**Methode `_build_assistant_turn` (Zeile ~1640):**

```python
# Vorher (Anthropic):
content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
return {"role": "assistant", "content": content}

# Nachher (OpenAI):
return {
    "role": "assistant",
    "content": response.content or "",
    "tool_calls": [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.name,
                "arguments": json.dumps(tc.arguments),
            },
        }
        for tc in response.tool_calls
    ],
}
```

**Methode `_build_tool_result_turn` (Zeile ~1650):**

```python
# Vorher (Anthropic):
return {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": r.tool_call_id, "content": r.content, "is_error": r.is_error}
    for r in tool_results
]}

# Nachher (OpenAI) — pro Result eine eigene Message, daher Liste zurückgeben:
# ACHTUNG: Rückgabetyp ändert sich von dict zu list[dict]
# → Aufrufstelle in agent.py muss angepasst werden (messages.extend statt messages.append)
return [
    {"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content}
    for r in tool_results
]
```

**Aufrufstelle (Zeile ~1108):**
```python
# Vorher:
messages.append(self._build_tool_result_turn(tool_results))

# Nachher:
messages.extend(self._build_tool_result_turn(tool_results))
```

---

### 2. `openforexai/adapters/llm/anthropic.py`

Neue statische Methode `_sanitize_messages` hinzufügen, die OpenAI → Anthropic konvertiert:

```python
@staticmethod
def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Konvertiert OpenAI-Format in Anthropic-Format."""
    result = []
    # Tool-Messages (role=tool) sammeln und zu einem User-Block zusammenfassen
    pending_tool_results = []

    for msg in messages:
        role = msg.get("role")

        if role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            })
            continue

        # Pending tool results vor dem nächsten non-tool-Message flushen
        if pending_tool_results:
            result.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

        if role == "assistant" and msg.get("tool_calls"):
            content: list[dict] = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except Exception:
                    args = {}
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": fn["name"],
                    "input": args,
                })
            result.append({"role": "assistant", "content": content})
        else:
            result.append(msg)

    # Trailing tool results flushen
    if pending_tool_results:
        result.append({"role": "user", "content": pending_tool_results})

    return result
```

`_sanitize_messages` in `complete_with_tools` aufrufen:
```python
effective_messages = _inject_images_anthropic(
    self._sanitize_messages(clean_messages), ...
)
```

---

### 3. `openforexai/adapters/llm/azure.py`

`_convert_message` und `_sanitize_messages` **entfernen** — nicht mehr benötigt.

`complete_with_tools` zurück auf einfaches Pass-through:
```python
full_messages = [{"role": "system", "content": clean_system}] + list(effective_messages)
```

---

### 4. `openforexai/adapters/llm/openai.py`, `lmstudio.py`, `ollama.py`

Prüfen ob `complete_with_tools` vorhanden ist. Falls ja:
- Keine Konvertierung nötig — Messages sind bereits im richtigen Format
- Sicherstellen dass kein `_sanitize_message` (Singular, alt) noch aufgerufen wird

---

### 5. `openforexai/ports/llm.py`

`_strip_messages_comments` prüfen — die Funktion durchsucht Messages nach
`type: "text"` Blöcken (Anthropic-Stil). Nach der Umstellung hat kein Message
mehr solche Blöcke im kanonischen Format.

```python
# Aktuell: behandelt Anthropic-Blöcke
elif isinstance(content, list):
    for block in content:
        if block.get('type') == 'text': ...

# Nach Umstellung: nur noch String-Content relevant
# List-Content kommt nicht mehr vor (außer image_url im User-Turn)
# → Funktion bleibt kompatibel, aber der elif-Zweig ist de facto dead code
# → optional aufräumen
```

---

## Risiken / Edge Cases

| Risiko | Beschreibung |
|---|---|
| Mehrere Tool-Results | OpenAI = N separate Messages; Anthropic = 1 User-Message. Konvertierung muss consecutive `role: "tool"` Messages korrekt zusammenfassen. |
| `arguments` als JSON-String | In OpenAI ist `function.arguments` ein JSON-**String**, nicht ein Dict. Anthropic will ein Dict (`input`). Nicht vergessen beim Hin- und Rückkonvertieren. |
| Leerer `content` | Bei reinen Tool-Call-Turns hat OpenAI `content: ""` oder `null`. Anthropic erlaubt das nicht — dort muss `content` immer mindestens ein Block sein. |
| `_strip_messages_comments` | Prüfen ob der List-Content-Zweig nach der Umstellung noch gebraucht wird (für image_url User-Turns). |
| Transcript-Logging | Azure schreibt Messages ins Transcript — nach Entfernen von `_sanitize_messages` werden dort direkt die OpenAI-Format-Messages geloggt. Kein funktionales Problem. |

---

## Teststrategie

1. Einen Turn mit Tool-Call gegen Anthropic testen → `get_open_positions` muss ausgeführt werden
2. Denselben Turn gegen Azure testen → gleiche Antwort, kein `tool_use`-Fehler
3. Multi-Turn (2+ Tool-Calls hintereinander) testen → History-Aufbau korrekt
4. Kein LLM-Provider darf einen 400-Fehler wegen falschem Message-Format werfen
