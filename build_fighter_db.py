import json
import re
import string
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE = "http://ufcstats.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


@dataclass
class FighterRecord:
    name: str
    first_name: str
    last_name: str
    profile_url: str
    height: Optional[str] = None
    weight: Optional[str] = None
    reach: Optional[str] = None
    stance: Optional[str] = None
    dob: Optional[str] = None

    slpm: Optional[float] = None
    str_acc: Optional[float] = None
    sapm: Optional[float] = None
    str_def: Optional[float] = None
    td_avg: Optional[float] = None
    td_acc: Optional[float] = None
    td_def: Optional[float] = None
    sub_avg: Optional[float] = None

    total_fights: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0

    ko_wins: int = 0
    sub_wins: int = 0
    dec_wins: int = 0

    ko_rate: float = 0.0
    sub_rate: float = 0.0
    decision_rate: float = 0.0
    finish_rate: float = 0.0


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_pct(text: str) -> Optional[float]:
    text = clean_text(text).replace("%", "")
    if not text or text == "--":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_float(text: str) -> Optional[float]:
    text = clean_text(text)
    if not text or text == "--":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def get_all_fighter_links() -> List[str]:
    links = []
    seen = set()

    for ch in string.ascii_lowercase:
        url = f"{BASE}/statistics/fighters?char={ch}&page=all"
        print(f"Fetching fighter list for {ch.upper()}...")
        soup = get_soup(url)

        for a in soup.select("a.b-link.b-link_style_black"):
            href = a.get("href")
            if href and "fighter-details" in href and href not in seen:
                seen.add(href)
                links.append(href)

        time.sleep(0.25)

    return links


def parse_bio_stats(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    result = {
        "first_name": "",
        "last_name": "",
        "height": None,
        "weight": None,
        "reach": None,
        "stance": None,
        "dob": None,
    }

    first = soup.select_one(".b-content__title-first")
    last = soup.select_one(".b-content__title-last")

    if first:
        result["first_name"] = clean_text(first.get_text())
    if last:
        result["last_name"] = clean_text(last.get_text())

    items = soup.select("li.b-list__box-list-item")
    for li in items:
        text = clean_text(li.get_text(" "))
        low = text.lower()

        if "height:" in low:
            result["height"] = text.split(":", 1)[1].strip()
        elif "weight:" in low:
            result["weight"] = text.split(":", 1)[1].strip()
        elif "reach:" in low:
            result["reach"] = text.split(":", 1)[1].strip()
        elif "stance:" in low:
            result["stance"] = text.split(":", 1)[1].strip()
        elif "dob:" in low:
            result["dob"] = text.split(":", 1)[1].strip()

    return result


def parse_performance_stats(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    stats = {
        "slpm": None,
        "str_acc": None,
        "sapm": None,
        "str_def": None,
        "td_avg": None,
        "td_acc": None,
        "td_def": None,
        "sub_avg": None,
    }

    items = soup.select("li.b-list__box-list-item")
    for li in items:
        text = clean_text(li.get_text(" "))
        low = text.lower()

        if "slpm:" in low:
            stats["slpm"] = parse_float(text.split(":", 1)[1])
        elif "str. acc.:" in low or "str acc:" in low:
            stats["str_acc"] = parse_pct(text.split(":", 1)[1])
        elif "sapm:" in low:
            stats["sapm"] = parse_float(text.split(":", 1)[1])
        elif "str. def:" in low or "str def:" in low:
            stats["str_def"] = parse_pct(text.split(":", 1)[1])
        elif "td avg.:" in low or "td avg:" in low:
            stats["td_avg"] = parse_float(text.split(":", 1)[1])
        elif "td acc.:" in low or "td acc:" in low:
            stats["td_acc"] = parse_pct(text.split(":", 1)[1])
        elif "td def.:" in low or "td def:" in low:
            stats["td_def"] = parse_pct(text.split(":", 1)[1])
        elif "sub. avg.:" in low or "sub avg:" in low:
            stats["sub_avg"] = parse_float(text.split(":", 1)[1])

    return stats


def normalize_method(method_text: str) -> str:
    m = method_text.lower()
    if "ko/tko" in m or "tko" in m or "ko" in m:
        return "ko"
    if "submission" in m:
        return "sub"
    if "decision" in m:
        return "dec"
    return "other"


def parse_fight_history(soup: BeautifulSoup) -> Dict[str, int]:
    summary = {
        "total_fights": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "ko_wins": 0,
        "sub_wins": 0,
        "dec_wins": 0,
    }

    rows = soup.select("tr.b-fight-details__table-row")
    for row in rows:
        cols = row.select("td")
        if len(cols) < 8:
            continue

        row_text = clean_text(row.get_text(" "))
        if not row_text:
            continue

        summary["total_fights"] += 1

        result_cell = clean_text(cols[0].get_text(" "))
        method_cell = clean_text(cols[7].get_text(" ")) if len(cols) > 7 else ""

        result_low = result_cell.lower()
        method_norm = normalize_method(method_cell)

        if result_low.startswith("win") or result_low == "w":
            summary["wins"] += 1
            if method_norm == "ko":
                summary["ko_wins"] += 1
            elif method_norm == "sub":
                summary["sub_wins"] += 1
            elif method_norm == "dec":
                summary["dec_wins"] += 1
        elif result_low.startswith("loss") or result_low == "l":
            summary["losses"] += 1
        else:
            summary["draws"] += 1

    return summary


def compute_rates(f: FighterRecord) -> FighterRecord:
    if f.wins > 0:
        f.ko_rate = round(f.ko_wins / f.wins, 4)
        f.sub_rate = round(f.sub_wins / f.wins, 4)
        f.decision_rate = round(f.dec_wins / f.wins, 4)
        f.finish_rate = round((f.ko_wins + f.sub_wins) / f.wins, 4)
    return f


def parse_fighter(url: str) -> FighterRecord:
    soup = get_soup(url)

    bio = parse_bio_stats(soup)
    perf = parse_performance_stats(soup)
    hist = parse_fight_history(soup)

    full_name = f'{bio["first_name"]} {bio["last_name"]}'.strip()

    fighter = FighterRecord(
        name=full_name,
        first_name=bio["first_name"],
        last_name=bio["last_name"],
        profile_url=url,
        height=bio["height"],
        weight=bio["weight"],
        reach=bio["reach"],
        stance=bio["stance"],
        dob=bio["dob"],
        slpm=perf["slpm"],
        str_acc=perf["str_acc"],
        sapm=perf["sapm"],
        str_def=perf["str_def"],
        td_avg=perf["td_avg"],
        td_acc=perf["td_acc"],
        td_def=perf["td_def"],
        sub_avg=perf["sub_avg"],
        total_fights=hist["total_fights"],
        wins=hist["wins"],
        losses=hist["losses"],
        draws=hist["draws"],
        ko_wins=hist["ko_wins"],
        sub_wins=hist["sub_wins"],
        dec_wins=hist["dec_wins"],
    )

    return compute_rates(fighter)


def build_database() -> List[Dict]:
    links = get_all_fighter_links()
    data = []
    total = len(links)

    for i, url in enumerate(links, start=1):
        try:
            fighter = parse_fighter(url)
            data.append(asdict(fighter))
            print(f"[{i}/{total}] OK - {fighter.name}")
        except Exception as e:
            print(f"[{i}/{total}] FAIL - {url} - {e}")

        time.sleep(0.3)

    return data


def main():
    data = build_database()

    with open("fighters.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Saved {len(data)} fighters to fighters.json")


if __name__ == "__main__":
    main()
