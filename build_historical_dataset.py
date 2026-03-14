import csv
import re
import string
import time
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

BASE = "http://ufcstats.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
OUTFILE = "historical_fights.csv"


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def get_all_fighters() -> List[Dict[str, str]]:
    fighters: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for ch in string.ascii_lowercase:
        url = f"{BASE}/statistics/fighters?char={ch}&page=all"
        print(f"Fetching fighter list for {ch.upper()}...")
        soup = get_soup(url)

        rows = soup.select("tr.b-statistics__table-row")
        for row in rows:
            links = row.select("a.b-link.b-link_style_black")
            if len(links) < 2:
                continue

            first_name = clean_text(links[0].get_text())
            last_name = clean_text(links[1].get_text())
            href = links[0].get("href") or links[1].get("href")

            if not href or "fighter-details" not in href:
                continue

            full_name = f"{first_name} {last_name}".strip()
            if not full_name or href in seen:
                continue

            seen.add(href)
            fighters.append(
                {
                    "name": full_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "profile_url": href,
                }
            )

        time.sleep(0.2)

    return fighters


def normalize_method(method_text: str) -> str:
    t = method_text.lower()
    if "ko/tko" in t or "tko" in t or re.search(r"\bko\b", t):
        return "ko"
    if "submission" in t:
        return "sub"
    if "decision" in t:
        return "dec"
    return "other"


def normalize_result(result_text: str) -> str:
    t = result_text.lower().strip()
    if t.startswith("win") or t == "w":
        return "W"
    if t.startswith("loss") or t == "l":
        return "L"
    if "draw" in t or t == "d":
        return "D"
    if "nc" in t or "no contest" in t:
        return "NC"
    return "UNK"


def extract_opponent_name(cell) -> str:
    pieces = [clean_text(x.get_text()) for x in cell.select("p")]
    pieces = [p for p in pieces if p]
    if len(pieces) >= 2:
        return pieces[1]
    text = clean_text(cell.get_text(" "))
    return text


def parse_event_and_date(cell) -> Tuple[str, str]:
    pieces = [clean_text(x.get_text()) for x in cell.select("p")]
    pieces = [p for p in pieces if p]
    if len(pieces) >= 2:
        return pieces[0], pieces[1]
    text = clean_text(cell.get_text(" "))
    return text, ""


def scrape_fighter_history(fighter_meta: Dict[str, str]) -> List[Dict[str, str]]:
    soup = get_soup(fighter_meta["profile_url"])
    rows = soup.select("tr.b-fight-details__table-row")

    out: List[Dict[str, str]] = []

    for row in rows:
        cols = row.select("td")
        if len(cols) < 10:
            continue

        result = normalize_result(clean_text(cols[0].get_text(" ")))
        opponent = extract_opponent_name(cols[1])
        event_name, event_date = parse_event_and_date(cols[6])
        method_raw = clean_text(cols[7].get_text(" "))
        round_text = clean_text(cols[8].get_text(" "))
        time_text = clean_text(cols[9].get_text(" "))

        if result not in {"W", "L", "D"}:
            continue
        if not opponent:
            continue

        out.append(
            {
                "fighter_name": fighter_meta["name"],
                "opponent_name": opponent,
                "result": result,
                "method_raw": method_raw,
                "method_group": normalize_method(method_raw),
                "event_name": event_name,
                "event_date": event_date,
                "round": round_text,
                "fight_time": time_text,
                "profile_url": fighter_meta["profile_url"],
            }
        )

    return out


def dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[Tuple[str, str, str, str]] = set()
    deduped: List[Dict[str, str]] = []

    for row in rows:
        fighter = row["fighter_name"]
        opp = row["opponent_name"]
        names = tuple(sorted([fighter, opp]))
        key = (row["event_name"], row["event_date"], names[0], names[1])

        # keep both mirrored rows out; one row per fight pairing
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    return deduped


def main():
    fighters = get_all_fighters()
    print(f"Found {len(fighters)} fighter profile links")

    all_rows: List[Dict[str, str]] = []

    for i, fighter in enumerate(fighters, start=1):
        try:
            rows = scrape_fighter_history(fighter)
            all_rows.extend(rows)
            print(f"[{i}/{len(fighters)}] OK - {fighter['name']} ({len(rows)} fights)")
        except Exception as e:
            print(f"[{i}/{len(fighters)}] FAIL - {fighter['name']} - {e}")

        time.sleep(0.15)

    deduped = dedupe_rows(all_rows)

    fieldnames = [
        "fighter_name",
        "opponent_name",
        "result",
        "method_raw",
        "method_group",
        "event_name",
        "event_date",
        "round",
        "fight_time",
        "profile_url",
    ]

    with open(OUTFILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)

    print(f"Saved {len(deduped)} rows to {OUTFILE}")


if __name__ == "__main__":
    main()
