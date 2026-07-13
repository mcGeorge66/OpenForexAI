#!/usr/bin/env python3

import argparse
from datetime import datetime, timedelta, timezone

from mql5_calendar_lib import find_event_ids


DEFAULT_JSON_FILE = r"C:\Users\zentr\AppData\Roaming\MetaQuotes\Terminal\Common\Files\economic_calendar.json"


def main():
    parser = argparse.ArgumentParser(
        description="List event_ids for economic calendar events in the next 4 hours."
    )

    parser.add_argument(
        "--json",
        default=DEFAULT_JSON_FILE,
        help="Path to economic_calendar.json",
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=10,
        help="Number of hours to look ahead. Default: 4",
    )

    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    start = now - timedelta(hours=1)

    until = now + timedelta(hours=args.hours)

    event_ids = find_event_ids(
        json_file=args.json,
        time_op="between",
        time_from=start,
        time_to=until,
        currencies=["USD", "EUR"],
    )

    for event_id in event_ids:
        print(event_id)


if __name__ == "__main__":
    main()