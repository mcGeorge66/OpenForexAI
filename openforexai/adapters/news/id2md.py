#!/usr/bin/env python3

import argparse
from mql5_calendar_lib import create_event_markdown


parser = argparse.ArgumentParser()
parser.add_argument("event_id")
parser.add_argument("--json", default="economic_calendar.json")
parser.add_argument("--out", default=None)
parser.add_argument("--language", default="en")

args = parser.parse_args()

path = create_event_markdown(
    json_file=args.json,
    event_id=args.event_id,
    out_file=args.out,
    language=args.language,
)

print(path)