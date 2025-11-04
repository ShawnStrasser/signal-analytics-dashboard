"""
Utility helpers for selecting a daily joke from multiple sources.
"""

from __future__ import annotations

import base64
import csv
import json
import random
import threading
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

from config import SUBSCRIPTION_DB_PATH

LOCAL_JOKES_PATH = Path(__file__).resolve().parents[1] / "static" / "jokes.csv"
LOCAL_USER_AGENT = "signal-analytics-dashboard/1.0"
STATE_FILE_PATH = Path(SUBSCRIPTION_DB_PATH).resolve().with_name("joke_state.json")

MAX_XKCD_DIMENSION = 800
APPROVED_XKCD_COMICS = [
    26, 55, 58, 149, 162, 208, 221, 227, 237, 246, 272, 281, 284, 285,
    302, 303, 325, 327, 386, 390, 421, 435, 451, 470, 483, 552, 557,
    605, 610, 612, 616, 626, 627, 833, 844, 927, 979, 1162, 1172, 1425,
    1667, 1741, 1831, 1906, 2054, 2228, 2347, 2610
]

_state_lock = threading.RLock()
_state_cache: Optional[Dict[str, Any]] = None

_daily_joke_lock = threading.RLock()
_cached_joke_date: Optional[date] = None
_cached_joke_payload: Optional[Dict[str, Any]] = None

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


def _serialize_joke_for_state(joke: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a joke payload into a JSON-serializable structure."""
    serialized: Dict[str, Any] = {}
    for key, value in joke.items():
        if isinstance(value, bytes):
            encoded = base64.b64encode(value).decode("ascii")
            serialized[key] = {"type": "bytes", "data": encoded}
        elif isinstance(value, tuple):
            serialized[key] = list(value)
        else:
            serialized[key] = value
    return serialized


def _deserialize_joke_from_state(raw_payload: Any) -> Optional[Dict[str, Any]]:
    """Reconstruct a joke payload from the serialized state representation."""
    if not isinstance(raw_payload, dict):
        return None

    reconstructed: Dict[str, Any] = {}
    for key, value in raw_payload.items():
        if isinstance(value, dict) and value.get("type") == "bytes":
            data = value.get("data")
            if not isinstance(data, str):
                return None
            try:
                reconstructed[key] = base64.b64decode(data)
            except (ValueError, TypeError):
                return None
        elif key in {"dimensions", "dpi"} and isinstance(value, list):
            reconstructed[key] = tuple(value)
        else:
            reconstructed[key] = value
    return reconstructed


def _ensure_state_locked() -> Dict[str, Any]:
    """Load or initialize the persistent joke state."""
    global _state_cache  # pylint: disable=global-statement
    global _cached_joke_date, _cached_joke_payload  # pylint: disable=global-statement
    if _state_cache is not None:
        return _state_cache

    try:
        with STATE_FILE_PATH.open(encoding="utf-8") as handle:
            raw_state = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_state = {}

    def _normalize(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed >= 0 else 0

    _state_cache = {
        "local_index": _normalize(raw_state.get("local_index")),
        "xkcd_index": _normalize(raw_state.get("xkcd_index")),
        "daily_joke": None,
    }

    daily_raw = raw_state.get("daily_joke")
    if isinstance(daily_raw, dict):
        raw_date = daily_raw.get("date")
        raw_payload = daily_raw.get("payload")
        if isinstance(raw_date, str):
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                parsed_date = None
        else:
            parsed_date = None

        payload = _deserialize_joke_from_state(raw_payload) if parsed_date else None
        if parsed_date and payload:
            _cached_joke_date = parsed_date
            _cached_joke_payload = payload
            _state_cache["daily_joke"] = {
                "date": parsed_date.isoformat(),
                "payload": _serialize_joke_for_state(payload),
            }

    return _state_cache


def _save_state_locked(state: Dict[str, Any]) -> None:
    """Persist the in-memory joke state to disk."""
    global _state_cache  # pylint: disable=global-statement
    STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = {
        "local_index": int(state.get("local_index", 0)),
        "xkcd_index": int(state.get("xkcd_index", 0)),
    }
    daily = state.get("daily_joke")
    if isinstance(daily, dict) and isinstance(daily.get("date"), str) and isinstance(daily.get("payload"), dict):
        serialized["daily_joke"] = daily
    else:
        serialized["daily_joke"] = None
    with STATE_FILE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(serialized, handle, separators=(",", ":"), sort_keys=True)
    _state_cache = {
        "local_index": serialized["local_index"],
        "xkcd_index": serialized["xkcd_index"],
        "daily_joke": serialized.get("daily_joke"),
    }


def get_local_joke() -> Optional[Dict[str, str]]:
    _load_local_jokes()
    jokes = _local_jokes_cache
    if not jokes:
        return None

    with _state_lock:
        state = _ensure_state_locked()
        index = int(state.get("local_index", 0))
        if index >= len(jokes):
            return None
        text = jokes[index]
        state["local_index"] = index + 1
        _save_state_locked(state)

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


def _fetch_xkcd_comic(comic_number: int) -> Optional[Dict[str, Any]]:
    """Retrieve and normalize a single XKCD comic payload."""
    try:
        info_response = requests.get(
            f"https://xkcd.com/{comic_number}/info.0.json",
            headers={"User-Agent": LOCAL_USER_AGENT},
            timeout=8,
        )
        if not info_response.ok:
            return None

        info = info_response.json()
        image_url = info.get("img")
        if not image_url:
            return None

        image_response = requests.get(
            image_url,
            headers={"User-Agent": LOCAL_USER_AGENT},
            timeout=8,
        )
        if not image_response.ok:
            return None

        img_data = BytesIO(image_response.content)
        with Image.open(img_data) as img:
            dpi_info = img.info.get("dpi")
            width, height = img.size
            if width > MAX_XKCD_DIMENSION or height > MAX_XKCD_DIMENSION:
                return None

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

            return {
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
    except (requests.RequestException, OSError):
        return None

    return None


def get_xkcd_comic(comic_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if comic_number is not None:
        try:
            specific = int(comic_number)
        except (TypeError, ValueError):
            return None
        return _fetch_xkcd_comic(specific)

    with _state_lock:
        state = _ensure_state_locked()
        index = int(state.get("xkcd_index", 0))
        if index >= len(APPROVED_XKCD_COMICS):
            return None
        target = APPROVED_XKCD_COMICS[index]

    comic = _fetch_xkcd_comic(target)
    if comic:
        with _state_lock:
            state = _ensure_state_locked()
            current_index = int(state.get("xkcd_index", 0))
            if current_index == index:
                state["xkcd_index"] = index + 1
                _save_state_locked(state)

    return comic


def get_random_joke() -> Dict[str, Any]:
    """Return a joke from a random source, falling back to local content."""
    sources = [get_xkcd_comic, get_joke_from_api, get_dad_joke, get_local_joke]
    random.shuffle(sources)

    for provider in sources:
        joke = provider()
        if joke and joke.get("text"):
            return joke

    return {"text": "No joke available today.", "source": "Fallback"}


def _get_daily_joke_payload(report_date: date) -> Dict[str, Any]:
    """Fetch the joke for the requested report date, caching in memory and on disk."""
    target_date = report_date or date.today()
    date_key = target_date.isoformat()

    with _daily_joke_lock:
        global _cached_joke_date, _cached_joke_payload  # pylint: disable=global-statement
        if _cached_joke_date == target_date and _cached_joke_payload:
            return dict(_cached_joke_payload)

        with _state_lock:
            state = _ensure_state_locked()
            daily = state.get("daily_joke")
            if isinstance(daily, dict) and daily.get("date") == date_key:
                payload = _deserialize_joke_from_state(daily.get("payload"))
                if payload:
                    _cached_joke_date = target_date
                    _cached_joke_payload = payload
                    return dict(payload)

        joke_payload = get_random_joke()
        payload_copy = dict(joke_payload)
        serialized_payload = _serialize_joke_for_state(payload_copy)

        with _state_lock:
            state = _ensure_state_locked()
            state["daily_joke"] = {"date": date_key, "payload": serialized_payload}
            _save_state_locked(state)

        _cached_joke_date = target_date
        _cached_joke_payload = payload_copy
        return dict(payload_copy)


def prepare_joke(report_date: date) -> Dict[str, Any]:
    """Select and decorate the joke payload for the report."""
    joke_payload = _get_daily_joke_payload(report_date)

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





