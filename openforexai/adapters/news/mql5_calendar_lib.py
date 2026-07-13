#!/usr/bin/env python3
# mql5_calendar_lib.py

from __future__ import annotations

import json
import re
import unicodedata
import requests

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal
from markdownify import markdownify as md
from pathlib import Path


TimeOperator = Literal["gt", "gte", "eq", "lt", "lte", "between"]


def slugify_country_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def load_events(json_file: str | Path) -> list[dict[str, Any]]:
    json_path = Path(json_file)

    with json_path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if isinstance(data, dict) and isinstance(data.get("events"), list):
        return data["events"]

    if isinstance(data, list):
        return data

    raise ValueError("JSON must be a list or contain an 'events' list.")


def build_mql5_url(event: dict[str, Any], language: str = "en") -> str:
    country_name = event.get("country_name")
    event_code = event.get("event_code")

    if not country_name:
        raise ValueError("Missing country_name in event record.")

    if not event_code:
        raise ValueError("Missing event_code in event record.")

    country_slug = slugify_country_name(str(country_name))

    return f"https://www.mql5.com/{language}/economic-calendar/{country_slug}/{event_code}"


def parse_time(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    value = str(value).strip()

    if value == "":
        return None

    # Unterstützt auch ISO-Strings mit Z
    value = value.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime format: {value}") from exc


def normalize_string_list(values: Iterable[str] | None) -> set[str] | None:
    if values is None:
        return None

    result = {str(v).strip().lower() for v in values if str(v).strip() != ""}

    return result if result else None


def normalize_int_list(values: Iterable[int | str] | None) -> set[int] | None:
    if values is None:
        return None

    result: set[int] = set()

    for value in values:
        if value is None or str(value).strip() == "":
            continue

        result.add(int(value))

    return result if result else None


def matches_time_filter(
    event: dict[str, Any],
    time_op: TimeOperator | None = None,
    time_value: str | datetime | None = None,
    time_from: str | datetime | None = None,
    time_to: str | datetime | None = None,
) -> bool:
    if time_op is None:
        return True

    event_time = parse_time(event.get("time_server"))

    if event_time is None:
        return False

    if time_op == "between":
        start = parse_time(time_from)
        end = parse_time(time_to)

        if start is None or end is None:
            raise ValueError("time_op='between' requires time_from and time_to.")

        return start <= event_time <= end

    compare_time = parse_time(time_value)

    if compare_time is None:
        raise ValueError(f"time_op='{time_op}' requires time_value.")

    if time_op == "gt":
        return event_time > compare_time

    if time_op == "gte":
        return event_time >= compare_time

    if time_op == "eq":
        return event_time == compare_time

    if time_op == "lt":
        return event_time < compare_time

    if time_op == "lte":
        return event_time <= compare_time

    raise ValueError(f"Unsupported time_op: {time_op}")


def find_event(
    json_file: str | Path,
    event_id: str | int,
    language: str = "en",
) -> dict[str, Any]:
    """
    Findet ein Event per event_id.

    Rückgabe:
      kompletter JSON-Abschnitt des Events
      plus berechnete URL im Feld: mql5_url
    """
    events = load_events(json_file)
    wanted = str(event_id)

    for event in events:
        if str(event.get("event_id")) == wanted:
            result = deepcopy(event)
            result["mql5_url"] = build_mql5_url(result, language=language)
            return result

    raise ValueError(f"event_id not found: {event_id}")


def find_event_ids(
    json_file: str | Path,
    *,
    time_op: TimeOperator | None = None,
    time_value: str | datetime | None = None,
    time_from: str | datetime | None = None,
    time_to: str | datetime | None = None,
    importance_codes: Iterable[int | str] | None = None,
    country_names: Iterable[str] | None = None,
    currencies: Iterable[str] | None = None,
) -> list[str]:
    """
    Findet Events anhand kombinierbarer Filter.

    Alle gesetzten Filter werden per UND verknüpft.

    time_op:
      "gt"       größer als time_value
      "gte"      größer/gleich time_value
      "eq"       gleich time_value
      "lt"       kleiner als time_value
      "lte"      kleiner/gleich time_value
      "between"  zwischen time_from und time_to, inkl. Grenzen

    Rückgabe:
      Liste von event_id Strings
    """
    events = load_events(json_file)

    importance_filter = normalize_int_list(importance_codes)
    country_filter = normalize_string_list(country_names)
    currency_filter = normalize_string_list(currencies)

    result: list[str] = []

    for event in events:
        if not matches_time_filter(
            event,
            time_op=time_op,
            time_value=time_value,
            time_from=time_from,
            time_to=time_to,
        ):
            continue

        if importance_filter is not None:
            try:
                event_importance = int(event.get("importance_code"))
            except (TypeError, ValueError):
                continue

            if event_importance not in importance_filter:
                continue

        if country_filter is not None:
            event_country = str(event.get("country_name", "")).strip().lower()

            if event_country not in country_filter:
                continue

        if currency_filter is not None:
            event_currency = str(event.get("currency", "")).strip().lower()

            if event_currency not in currency_filter:
                continue

        event_id = event.get("event_id")

        if event_id is not None:
            result.append(str(event_id))

    return result


def create_event_markdown(
    json_file,
    event_id,
    out_file=None,
    language="en",
):
    import requests
    from pathlib import Path
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    event = find_event(json_file, event_id, language)
    url = event["mql5_url"]

    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 OpenForexAI Calendar Fetcher"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Alles entfernen, was im Markdown nichts zu suchen hat
    for tag in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "header",
        "footer",
        "nav",
        "aside",
        "form",
    ]):
        tag.decompose()

    # Erst versuchen, den eigentlichen Kalender-Inhalt zu greifen
    content = (
        soup.find("div", id="eventContentPanel")
        or soup.find("main")
        or soup.find("article")
        or soup.body
    )

    if content is None:
        raise RuntimeError("Could not find useful page content.")

    markdown = md(
        str(content),
        heading_style="ATX",
        strip=["img"],
    ).strip()

    # Mehrfach-Leerzeilen reduzieren
    import re
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    output_path = Path(out_file) if out_file else Path(
        f"{event.get('event_id')}_{event.get('event_code')}.md"
    )

    header = (
        f"<!--\n"
        f"event_id: {event.get('event_id')}\n"
        f"name: {event.get('name')}\n"
        f"currency: {event.get('currency')}\n"
        f"url: {url}\n"
        f"-->\n\n"
    )

    output_path.write_text(header + markdown, encoding="utf-8")
    return output_path


def create_events_markdown(
    json_file,
    event_ids,
    out_file,
    language="en",
):
    import requests
    from pathlib import Path
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
    import re

    if not event_ids:
        raise ValueError("event_ids must not be empty.")

    output_path = Path(out_file)
    sections = []

    for event_id in event_ids:
        event = find_event(json_file, event_id, language)
        url = event["mql5_url"]

        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 OpenForexAI Calendar Fetcher"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Alles entfernen, was im Markdown nichts zu suchen hat
        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "header",
            "footer",
            "nav",
            "aside",
            "form",
        ]):
            tag.decompose()

        # Erst versuchen, den eigentlichen Kalender-Inhalt zu greifen
        content = (
            soup.find("div", id="eventContentPanel")
            or soup.find("main")
            or soup.find("article")
            or soup.body
        )

        if content is None:
            raise RuntimeError(f"Could not find useful page content for event_id {event_id}.")

        markdown = md(
            str(content),
            heading_style="ATX",
            strip=["img"],
        ).strip()

        # Mehrfach-Leerzeilen reduzieren
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        section_header = (
            f"\n\n---\n\n"
            f"<!--\n"
            f"event_id: {event.get('event_id')}\n"
            f"name: {event.get('name')}\n"
            f"currency: {event.get('currency')}\n"
            f"event_code: {event.get('event_code')}\n"
            f"url: {url}\n"
            f"-->\n\n"
            f"# {event.get('name') or event.get('event_code') or event_id}\n\n"
        )

        sections.append(section_header + markdown)

    output_path.write_text("\n".join(sections).strip() + "\n", encoding="utf-8")
    return output_path