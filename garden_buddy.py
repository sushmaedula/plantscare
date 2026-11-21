#!/usr/bin/env python3
"""A tiny command-line journal for plants in a tropical-India garden."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any


DATA_FILE = Path("garden.json")
CATALOG_FILE = Path(__file__).with_name("plant_catalog.json")
CARE_TASKS = ("water", "prune", "fertilize")


def load_plants() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        plants = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read {DATA_FILE}: {exc}") from exc
    if not isinstance(plants, list):
        raise SystemExit(f"{DATA_FILE} should contain a JSON list of plants")

    # Migrate records made by the first Garden Buddy version.
    for plant in plants:
        if "care" not in plant and "water_every_days" in plant:
            plant["care"] = {
                "water": {
                    "every_days": plant.pop("water_every_days"),
                    "tracking_from": date.today().isoformat(),
                    "last_done": plant.pop("last_watered", None),
                }
            }
    return plants


def save_plants(plants: list[dict[str, Any]]) -> None:
    try:
        DATA_FILE.write_text(json.dumps(plants, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Could not save {DATA_FILE}: {exc}") from exc


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD, for example 2026-11-01") from exc


def positive_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("enter a whole number of days") from exc
    if days < 1:
        raise argparse.ArgumentTypeError("enter at least 1 day")
    return days


def find_plant(plants: list[dict[str, Any]], plant_id: str) -> dict[str, Any] | None:
    return next((plant for plant in plants if plant["id"] == plant_id), None)


def care_due_date(schedule: dict[str, Any]) -> date:
    anchor = schedule.get("last_done") or schedule["tracking_from"]
    return date.fromisoformat(anchor) + timedelta(days=schedule["every_days"])


def command_add(args: argparse.Namespace) -> None:
    configured = {
        task: getattr(args, f"{task}_every")
        for task in CARE_TASKS
        if getattr(args, f"{task}_every") is not None
    }
    if not configured:
        raise SystemExit("Choose at least one reminder, such as --water-every 4.")

    started = date.today().isoformat()
    plant = {
        "id": uuid.uuid4().hex[:6],
        "name": args.name,
        "care": {
            task: {"every_days": days, "tracking_from": started, "last_done": None}
            for task, days in configured.items()
        },
    }
    plants = load_plants()
    plants.append(plant)
    save_plants(plants)
    print(f"Added {plant['name']} (ID {plant['id']}). Reminders start from today.")


def command_list(_: argparse.Namespace) -> None:
    plants = load_plants()
    if not plants:
        print('No plants yet. See examples with: python3 garden_buddy.py catalog')
        return

    for plant in sorted(plants, key=lambda item: item["name"].casefold()):
        print(f"{plant['name']} (ID {plant['id']})")
        for task in CARE_TASKS:
            schedule = plant.get("care", {}).get(task)
            if not schedule:
                continue
            due = care_due_date(schedule)
            last_done = schedule.get("last_done")
            last_note = f"; last recorded {last_done}" if last_done else "; tracking starts from add date"
            print(f"  {task.title()}: every {schedule['every_days']} days; next due {due}{last_note}")


def command_due(_: argparse.Namespace) -> None:
    today = date.today()
    due_items = []
    for plant in load_plants():
        for task, schedule in plant.get("care", {}).items():
            due = care_due_date(schedule)
            if due <= today:
                due_items.append((due, plant["name"], plant["id"], task))

    if not due_items:
        print("No care reminders are due based on the intervals you entered.")
        return

    print("Care reminders due based on your schedule:")
    for due, name, plant_id, task in sorted(due_items):
        print(f"- {name}: {task} (ID {plant_id}; due {due.isoformat()})")


def command_log(args: argparse.Namespace) -> None:
    plants = load_plants()
    plant = find_plant(plants, args.plant_id)
    if plant is None:
        raise SystemExit(f"No plant found with ID {args.plant_id}.")
    schedule = plant.get("care", {}).get(args.task)
    if schedule is None:
        raise SystemExit(f"No {args.task} reminder is set for {plant['name']}.")
    completed = args.date or date.today()
    if completed > date.today():
        raise SystemExit("A completed care date cannot be in the future.")
    schedule["last_done"] = completed.isoformat()
    save_plants(plants)
    print(f"Recorded {args.task} for {plant['name']} on {completed.isoformat()}.")


def command_catalog(_: argparse.Namespace) -> None:
    try:
        entries = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read plant catalog: {exc}") from exc
    print("Starter plants with native ranges that include India:")
    for item in entries:
        print(f"- {item['common_name']} — {item['botanical_name']}")
    print("\nThe catalog has no preset care intervals; set reminders for your own conditions.")


def command_remove(args: argparse.Namespace) -> None:
    plants = load_plants()
    remaining = [plant for plant in plants if plant["id"] != args.plant_id]
    if len(remaining) == len(plants):
        raise SystemExit(f"No plant found with ID {args.plant_id}.")
    save_plants(remaining)
    print(f"Removed plant {args.plant_id}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Keep a simple journal of your garden plants.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="add a plant and optional care reminders")
    add.add_argument("name", help="plant name, such as Tulsi")
    add.add_argument("--water-every", type=positive_days, help="remind every N days")
    add.add_argument("--prune-every", type=positive_days, help="remind every N days")
    add.add_argument("--fertilize-every", type=positive_days, help="remind every N days")
    add.set_defaults(func=command_add)

    listing = commands.add_parser("list", help="show plants and their care schedules")
    listing.set_defaults(func=command_list)

    due = commands.add_parser("due", help="show care reminders that are due")
    due.set_defaults(func=command_due)

    log = commands.add_parser("log", help="record a completed care task")
    log.add_argument("plant_id", help="ID shown by the list command")
    log.add_argument("task", choices=CARE_TASKS, help="water, prune, or fertilize")
    log.add_argument("--date", type=parse_date, help="completion date; defaults to today")
    log.set_defaults(func=command_log)

    catalog = commands.add_parser("catalog", help="show the tropical-India starter plant list")
    catalog.set_defaults(func=command_catalog)

    remove = commands.add_parser("remove", help="remove a plant from your journal")
    remove.add_argument("plant_id", help="ID shown by the list command")
    remove.set_defaults(func=command_remove)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
