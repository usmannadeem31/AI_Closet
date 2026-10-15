"""Local AI Closet: infer, review, and save a garment; list saved items."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

FIELDS = ("category", "type", "color", "formality", "season", "brand")
CATEGORIES = {"top", "bottom", "outerwear", "dress", "footwear", "accessory", "other"}
PROJECT = Path(__file__).resolve().parent.parent


def validate(data):
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ValueError("Expected exactly these JSON fields: " + ", ".join(FIELDS))
    for key, value in data.items():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be a nonempty string or null.")
    if data["category"] is not None and data["category"] not in CATEGORIES:
        raise ValueError("category must be one of: " + ", ".join(sorted(CATEGORIES)))
    return data


def parse_prediction(raw):
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if match:
        text = match.group(1)
    return validate(json.loads(text))


def infer(image_bytes, base_url, model):
    from PIL import Image, ImageOps
    from openai import OpenAI

    with Image.open(io.BytesIO(image_bytes)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((512, 512))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    prompt = (
        "Catalog the main garment. Return only one JSON object with exactly "
        "category, type, color, formality, season, brand. "
        "Category must be top, bottom, outerwear, dress, footwear, accessory, "
        "other, or null. Use short strings for type and color. "
        "Formality is an estimate; use null when unclear. "
        "Use null for any uncertain field. Always set season and brand to null: "
        "the user will supply these during review. Do not include Markdown."
    )
    client = OpenAI(base_url=base_url, api_key="local", timeout=180, max_retries=0)
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + encoded}},
        ]}],
        temperature=0,
        max_tokens=256,
    )
    latency = time.perf_counter() - started
    choice = response.choices[0]
    if choice.finish_reason != "stop":
        raise ValueError(f"Incomplete response ({choice.finish_reason}); nothing saved.")
    raw = choice.message.content or ""
    try:
        predicted = parse_prediction(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid model output; nothing saved.\n{raw}\n{exc}") from exc
    return predicted, raw, latency, response.model


def review(predicted):
    candidate = predicted.copy()
    # These attributes require explicit user input in this initial catalog.
    candidate["season"] = None
    candidate["brand"] = None
    print("\nProposed entry (season and brand require your input):")
    print(json.dumps(candidate, indent=2))
    print("\nReview each field: Enter keeps it; '-' sets unknown.")
    for field in FIELDS:
        while True:
            answer = input(f"{field} [{candidate[field] or 'unknown'}]: ").strip()
            updated = candidate.copy()
            if answer:
                updated[field] = None if answer == "-" else answer
            try:
                candidate = validate(updated)
                break
            except ValueError as exc:
                print(exc)
    print("\nReviewed entry:")
    print(json.dumps(candidate, indent=2))
    if input("Save this entry? [y/N]: ").strip().lower() != "y":
        return None
    return candidate


def save_entry(db_path, image_bytes, source_path, predicted, reviewed, raw, model, latency):
    validate(reviewed)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image_bytes).hexdigest()
    item_id = "item_" + uuid.uuid4().hex[:12]
    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS wardrobe_items (
                item_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                source_path TEXT NOT NULL, image_sha256 TEXT NOT NULL UNIQUE,
                image_bytes BLOB NOT NULL, attributes_json TEXT NOT NULL,
                predicted_json TEXT NOT NULL, raw_response TEXT NOT NULL,
                model TEXT NOT NULL, request_seconds REAL NOT NULL,
                user_reviewed INTEGER NOT NULL CHECK (user_reviewed = 1)
            )
        """)
        previous = connection.execute(
            "SELECT item_id FROM wardrobe_items WHERE image_sha256 = ?", (digest,)
        ).fetchone()
        if previous:
            return previous[0], False
        connection.execute(
            "INSERT INTO wardrobe_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, datetime.now(timezone.utc).isoformat(), str(source_path), digest,
             image_bytes, json.dumps(reviewed), json.dumps(predicted), raw,
             model, latency, 1),
        )
    return item_id, True


def list_entries(db_path):
    if not db_path.exists():
        print("Your wardrobe is empty. Add and review a photo first.")
        return
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT item_id, attributes_json FROM wardrobe_items ORDER BY created_at"
        ).fetchall()
    for item_id, attributes in rows:
        print(item_id + "  " + attributes)
    print(f"{len(rows)} saved item(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=PROJECT / "data" / "wardrobe.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Analyze one photo, review, and save")
    add.add_argument("image", type=Path)
    add.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    add.add_argument("--model", default="ai-closet-local")
    commands.add_parser("list", help="List saved wardrobe entries")
    args = parser.parse_args()
    try:
        if args.command == "list":
            list_entries(args.db)
            return
        source = args.image.expanduser().resolve()
        image_bytes = source.read_bytes()
        print("Analyzing photo...")
        predicted, raw, latency, model = infer(image_bytes, args.base_url, args.model)
        print(f"Request time: {latency:.2f} seconds")
        reviewed = review(predicted)
        if reviewed is None:
            print("Cancelled. No wardrobe entry saved.")
            return
        item_id, created = save_entry(
            args.db, image_bytes, source, predicted, reviewed, raw, model, latency)
        print(("Saved: " if created else "This exact image is already saved: ") + item_id)
        print(f"Database: {args.db}")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
