"""Kein Zugriff im Simulator darf an der Produktion hängen.

Diese Prüfung ist absichtlich strukturell und nicht funktional. Genau dieser
Fehler ist passiert: die Werkzeuge lasen längst den Spiegel, das Kerzenfenster
darunter noch die Produktion — Chart und Werkzeug hätten sich widersprochen,
sobald der Spiegel nachhinkt. Ein Test, der einen Endpunkt aufruft, hätte das
nicht gesehen; er hätte nur den Weg geprüft, den er selbst nimmt.

Hier zählt der Quelltext: jeder Kerzen-Lesevorgang und jeder ToolContext in
einer Simulationsfunktion muss die Quelle mitführen. Kommt eine neue Funktion
dazu, fällt sie hier auf, nicht erst in einer Auswertung, die niemand mehr
einordnen kann.
"""
from __future__ import annotations

import ast
import pathlib

API = pathlib.Path(__file__).resolve().parents[2] / "openforexai" / "management" / "api.py"

# Die Funktionen, die den Simulator bedienen. Der Snapshot-Designer
# (`/config/snapshots/tool-preview`) steht bewusst nicht hier: er misst einen
# laufenden Agenten am echten Markt, das ist seine Aufgabe.
SIMULATION = {
    "_build_prompt_workbench_context",
    "prompt_workbench_chat",
    "prompt_workbench_simulate_step",
    "prompt_workbench_context_preview",
    "prompt_workbench_snapshot_preview",
}


def _simulation_functions() -> dict[str, ast.AST]:
    tree = ast.parse(API.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in SIMULATION:
            found[node.name] = node
    missing = SIMULATION - set(found)
    assert not missing, f"Funktion umbenannt oder entfernt, Prüfung läuft ins Leere: {missing}"
    return found


def _keyword(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _calls(node: ast.AST, *, attr: str | None = None, name: str | None = None):
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if attr and isinstance(f, ast.Attribute) and f.attr == attr:
            yield sub
        elif name and isinstance(f, ast.Name) and f.id == name:
            yield sub


def test_every_candle_window_comes_from_the_mirror() -> None:
    for fn_name, fn in _simulation_functions().items():
        for call in _calls(fn, attr="get_candles"):
            assert _keyword(call, "source") == "reporting", (
                f"{fn_name}, Zeile {call.lineno}: get_candles ohne source='reporting' "
                f"— das Fenster käme aus der Produktion")


def test_every_tool_context_carries_the_mirror() -> None:
    for fn_name, fn in _simulation_functions().items():
        for call in _calls(fn, name="ToolContext"):
            assert _keyword(call, "data_source") == "reporting", (
                f"{fn_name}, Zeile {call.lineno}: ToolContext ohne data_source='reporting' "
                f"— jedes Werkzeug darunter läse live")


def test_every_snapshot_is_built_from_the_mirror() -> None:
    for fn_name, fn in _simulation_functions().items():
        for call in _calls(fn, name="build_analysis_snapshot"):
            assert _keyword(call, "data_source") == "reporting", (
                f"{fn_name}, Zeile {call.lineno}: build_analysis_snapshot ohne "
                f"data_source='reporting' — jeder Tool-Block darunter läse live")


def test_the_check_actually_finds_something() -> None:
    """Sonst wäre ein grüner Lauf ohne Aussage möglich."""
    fns = _simulation_functions()
    n = sum(len(list(_calls(fn, name="ToolContext"))) for fn in fns.values())
    m = sum(len(list(_calls(fn, attr="get_candles"))) for fn in fns.values())
    k = sum(len(list(_calls(fn, name="build_analysis_snapshot"))) for fn in fns.values())
    assert (n, m, k) == (4, 2, 2), f"Struktur hat sich geändert: {n} Kontexte, {m} Fenster, {k} Snapshots"
