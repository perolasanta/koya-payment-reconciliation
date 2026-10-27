#!/usr/bin/env python3
"""Reconcile payment events and print the KOYA verification code."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


def parse_timestamp(value):
    """Parse an ISO-8601 timestamp and normalize it to UTC."""
    timestamp = datetime.fromisoformat(
        str(value).strip().replace("Z", "+00:00")
    )

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def parse_amount(value):
    """Convert a naira amount into an exact Decimal value."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Invalid payment amount: {value!r}")

    amount = str(value).strip()

    # Support common currency formatting.
    amount = amount.replace("\u00a0", "")
    amount = amount.replace("₦", "")
    amount = re.sub(r"NGN", "", amount, flags=re.IGNORECASE)
    amount = amount.replace(",", "")
    amount = re.sub(r"\s+", "", amount)

    try:
        result = Decimal(amount)
    except InvalidOperation as error:
        raise ValueError(
            f"Cannot parse payment amount: {value!r}"
        ) from error

    if not result.is_finite():
        raise ValueError(f"Non-finite payment amount: {value!r}")

    return result


def reconcile():
    # Resolve data files relative to this script.
    base_dir = Path(__file__).resolve().parent
    payments_file = base_dir / "payments.jsonl"
    expected_file = base_dir / "expected.txt"

    # txn_id -> (timestamp, line_number, event)
    latest_events = {}

    with payments_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file):
            # Ignore malformed JSON lines.
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(event, dict):
                continue

            # Ignore events without a transaction ID.
            txn_id = event.get("txn_id")

            if txn_id is None or not str(txn_id).strip():
                continue

            # All remaining events are expected to be valid.
            timestamp = parse_timestamp(event["ts"])
            previous = latest_events.get(txn_id)

            # The latest timestamp wins. For identical timestamps,
            # the event appearing later in the file wins.
            if previous is None or (
                timestamp,
                line_number,
            ) > (
                previous[0],
                previous[1],
            ):
                latest_events[txn_id] = (
                    timestamp,
                    line_number,
                    event,
                )

    # Only the latest successful attempt for each transaction counts.
    successful_events = [
        item[2]
        for item in latest_events.values()
        if item[2].get("status") == "success"
    ]

    count = len(successful_events)

    # Use Decimal for accurate monetary arithmetic.
    total = Decimal("0")

    for event in successful_events:
        total += parse_amount(event["amount"])

    # Validate the count against the finance team's expected count.
    with expected_file.open("r", encoding="utf-8") as file:
        expected = int(file.read().strip())

    if count != expected:
        print(
            f"Check failed: counted {count} successful payments, "
            f"expected {expected}."
        )
        print(
            "Something in the data isn't being handled "
            "the way the README describes."
        )
        return

    # Match the original script's integer-code format.
    rounded_total = round(total)

    print(f"Check passed: {count} successful payments.")
    print(f"Your code: KOYA-{rounded_total}")


if __name__ == "__main__":
    reconcile()