"""
Utility helpers for selecting a daily joke from multiple sources.
"""

from __future__ import annotations

import csv
import random
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

LOCAL_JOKES_PATH = Path(__file__).resolve().parents[1] / "static" / "jokes.csv"
LOCAL_USER_AGENT = "signal-analytics-dashboard/1.0"

MAX_XKCD_DIMENSION = 800
APPROVED_XKCD_COMICS = [
    26, 55, 58, 149, 162, 208, 221, 227, 237, 246, 272, 281, 284, 285,
    302, 303, 325, 327, 386, 390, 421, 435, 451, 470, 483, 552, 557,
    605, 610, 612, 616, 626, 627, 833, 844, 927, 979, 1162, 1172, 1425,
    1667, 1741, 1831, 1906, 2054, 2228, 2347, 2610
]

_local_jokes_cache: List[str] = []
_local_jokes_loaded = False


def _normalize_text(value: str) -> str:
    text = (value or "").strip()
    text = text.replace("\r\n", " ").replace("\n", " ")
    return " ".join(text.split())


def _load_local_jokes() -> None:
    global _local_jokes_loaded  # pylint: disable=global-statement
    if _local_jokes_loaded:
        return

    jokes: List[str] = []
    try:
        with LOCAL_JOKES_PATH.open(encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header_map: Dict[str, int] = {}
            for index, row in enumerate(reader):
                if not row:
                    continue

                normalized_row = [_normalize_text(cell) for cell in row]
                if index == 0:
                    lowered = [cell.lower() for cell in normalized_row]
                    if "joke" in lowered or "text" in lowered or "date" in lowered:
                        for pos, name in enumerate(lowered):
                            header_map[name] = pos
                        continue

                text_cell: Optional[str] = None
                for candidate in ("joke", "text"):
                    if candidate in header_map:
                        text_cell = normalized_row[header_map[candidate]]
                        break
                if text_cell is None:
                    text_cell = normalized_row[-1]

                normalized = _normalize_text(text_cell)
                if normalized:
                    jokes.append(normalized)
    except FileNotFoundError:
        jokes = []

    _local_jokes_cache.extend(jokes)
    _local_jokes_loaded = True


def get_local_joke() -> Optional[Dict[str, str]]:
    _load_local_jokes()
    jokes = _local_jokes_cache
    if not jokes:
        return None
    text = random.choice(jokes)
    return {"text": text, "source": "Local Library"}


def get_joke_from_api() -> Optional[Dict[str, Any]]:
    try:
        url = "https://v2.jokeapi.dev/joke/Any?safe-mode"
        response = requests.get(url, headers={"User-Agent": LOCAL_USER_AGENT}, timeout=6)
        if not response.ok:
            return None
        payload = response.json()
        if payload.get("type") == "single":
            joke = payload.get("joke")
            if not joke:
                return None
            return {"text": _normalize_text(joke), "source": "JokeAPI"}

        setup = payload.get("setup")
        delivery = payload.get("delivery")
        if setup and delivery:
            combined = f"{_normalize_text(setup)}\n{_normalize_text(delivery)}"
            return {"text": combined, "source": "JokeAPI"}
    except requests.RequestException:
        return None
    return None


def get_dad_joke() -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(
            "https://icanhazdadjoke.com/",
            headers={
                "Accept": "application/json",
                "User-Agent": LOCAL_USER_AGENT,
            },
            timeout=6,
        )
        if not response.ok:
            return None
        payload = response.json()
        joke = payload.get("joke")
        if not joke:
            return None
        return {"text": _normalize_text(joke), "source": "icanhazdadjoke"}
    except requests.RequestException:
        return None
    return None


def get_xkcd_comic(comic_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if comic_number is not None:
        try:
            specific = int(comic_number)
        except (TypeError, ValueError):
            specific = None
        remaining = [specific] if specific is not None else APPROVED_XKCD_COMICS[:]
    else:
        remaining = APPROVED_XKCD_COMICS[:]
        random.shuffle(remaining)

    while remaining:
        comic_number = remaining.pop()
        if comic_number is None:
            continue
        try:
            info_response = requests.get(
                f"https://xkcd.com/{comic_number}/info.0.json",
                headers={"User-Agent": LOCAL_USER_AGENT},
                timeout=8,
            )
            if not info_response.ok:
                continue

            info = info_response.json()
            image_url = info.get("img")
            if not image_url:
                continue

            image_response = requests.get(
                image_url,
                headers={"User-Agent": LOCAL_USER_AGENT},
                timeout=8,
            )
            if not image_response.ok:
                continue

            img_data = BytesIO(image_response.content)
            with Image.open(img_data) as img:
                dpi_info = img.info.get("dpi")
                width, height = img.size
                if width > MAX_XKCD_DIMENSION or height > MAX_XKCD_DIMENSION:
                    continue

                img = img.convert("RGB")
                if "icc_profile" in img.info:
                    img.info.pop("icc_profile", None)
                output = BytesIO()
                img.save(output, format="PNG")
                dpi_tuple: Optional[tuple[float, float]] = None
                if isinstance(dpi_info, (tuple, list)) and dpi_info:
                    try:
                        dpi_x = float(dpi_info[0]) or 0.0
                        dpi_y = float(dpi_info[1]) if len(dpi_info) > 1 else dpi_x
                        if dpi_x > 0 and dpi_y > 0:
                            dpi_tuple = (dpi_x, dpi_y)
                    except (TypeError, ValueError):
                        dpi_tuple = None

                result = {
                    "text": info.get("title") or "XKCD Comic",
                    "source": "XKCD",
                    "image": output.getvalue(),
                    "image_width": width,
                    "image_height": height,
                    "dimensions": (width, height),
                    "dpi": dpi_tuple,
                    "alt": info.get("alt"),
                    "comic_number": comic_number,
                }
                return result
        except (requests.RequestException, OSError):
            continue

    return None


def get_random_joke() -> Dict[str, Any]:
    """Return a joke from a random source, falling back to local content."""
    sources = [get_xkcd_comic, get_joke_from_api, get_dad_joke, get_local_joke]
    random.shuffle(sources)

    for provider in sources:
        joke = provider()
        if joke and joke.get("text"):
            return joke

    return {"text": "No joke available today.", "source": "Fallback"}



def prepare_joke(report_date: date) -> Dict[str, Any]:
    """Select and decorate the joke payload for the report."""
    joke_payload = get_random_joke()

    joke = dict(joke_payload)
    section_title = "Joke of the Week" if report_date.weekday() == 0 else "Daily Dose of Humor"
    joke["section_title"] = section_title

    source = (joke.get("source") or "").lower()
    if source == "jokeapi":
        joke["attribution"] = "Joke provided by JokeAPI (https://jokeapi.dev)"
    elif source == "icanhazdadjoke":
        joke["attribution"] = "Dad joke provided by icanhazdadjoke.com"
    elif source == "xkcd":
        link_id = joke.get("comic_number") or joke.get("link") or joke.get("id")
        try:
            link_id = int(link_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            link_id = None

        if link_id:
            joke["attribution"] = f"XKCD Comic #{link_id} - https://xkcd.com/{link_id}/"
        else:
            joke["attribution"] = "XKCD Comic - https://xkcd.com"
    else:
        attribution = joke.get("attribution")
        joke["attribution"] = attribution if attribution else None

    return joke





