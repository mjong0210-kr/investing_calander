"""
Investing.com Economic Calendar -> Telegram
- 매일 KST 06:00 실행 가능
- 중요도 2 이상
- 국가 순서: 미국, EU, 독일, 영국, 일본, 프랑스, 호주, 캐나다, 중국

주의:
Investing.com은 공식 공개 API가 아니므로 사이트 구조/차단 정책 변경 시 작동하지 않을 수 있습니다.
개인용/테스트용 자동화에 가깝게 사용하세요.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import pytz
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

KST = pytz.timezone("Asia/Seoul")
INVESTING_URL = "https://www.investing.com/economic-calendar/"
CALENDAR_ENDPOINT = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

# Investing.com 국가 ID는 사이트 변경 가능성이 있습니다.
# 아래 값은 널리 쓰이던 경제캘린더 country ID 기준입니다. 작동이 안 되면 README의 점검 방법 참고.
COUNTRY_ORDER = [
    ("미국", "united states", "5"),
    ("EU", "euro zone", "72"),
    ("독일", "germany", "17"),
    ("영국", "united kingdom", "4"),
    ("일본", "japan", "35"),
    ("프랑스", "france", "22"),
    ("호주", "australia", "25"),
    ("캐나다", "canada", "6"),
    ("중국", "china", "37"),
]
COUNTRY_ID_TO_KO = {cid: ko for ko, _en, cid in COUNTRY_ORDER}
COUNTRY_KO_ORDER = [ko for ko, _en, _cid in COUNTRY_ORDER]
COUNTRY_RANK = {ko: i for i, ko in enumerate(COUNTRY_KO_ORDER)}


@dataclass
class EconEvent:
    country: str
    time: str
    importance: int
    event: str
    actual: str
    forecast: str
    previous: str


def clean_text(value: str | None) -> str:
    if not value:
        return "-"
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value if value else "-"


def get_browser_session() -> requests.Session:
    """Playwright로 Investing.com을 1회 열어 세션 쿠키와 User-Agent를 확보."""
    session = requests.Session()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(INVESTING_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        user_agent = page.evaluate("() => navigator.userAgent")
        for cookie in context.cookies():
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))

        browser.close()

    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.investing.com",
            "Referer": INVESTING_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return session


def fetch_calendar_html(target_date: datetime) -> str:
    session = get_browser_session()
    date_str = target_date.strftime("%Y-%m-%d")
    country_ids = [cid for _ko, _en, cid in COUNTRY_ORDER]

    # 중요도 2, 3만 요청. 일부 시점에서 서버가 이 필터를 무시할 수 있어 파싱 후에도 재필터링함.
    data = {
        "dateFrom": date_str,
        "dateTo": date_str,
        "timeZone": "88",  # Asia/Seoul로 알려진 값. 미작동 시 페이지 시간대와 대조 필요.
        "timeFilter": "timeOnly",
        "currentTab": "today",
        "limit_from": "0",
        "importance[]": ["2", "3"],
        "countries[]": country_ids,
    }

    response = session.post(CALENDAR_ENDPOINT, data=data, timeout=30)
    response.raise_for_status()
    payload = response.json()

    html_table = payload.get("data") or payload.get("html") or ""
    if not html_table:
        raise RuntimeError(f"경제캘린더 HTML을 받지 못했습니다. 응답 키: {list(payload.keys())}")
    return html_table


def count_importance(row: Tag) -> int:
    """행 내부의 황소/별 아이콘 개수를 기반으로 중요도 계산."""
    # Investing.com은 importance를 bull 아이콘으로 표시하는 경우가 많음.
    class_text = " ".join(" ".join(v) if isinstance(v, list) else str(v) for v in row.get_attribute_list("class"))
    row_html = str(row)

    # 흔한 케이스: grayFullBullishIcon 또는 bullishIcon이 중요도만큼 등장
    count = row_html.count("grayFullBullishIcon") + row_html.count("bullishIcon")
    if count > 0:
        return min(count, 3)

    # data-img_key="bull2" 같은 변형 대비
    match = re.search(r"bull(\d)", row_html, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # 알 수 없으면 0 처리해 제외
    return 0


def extract_country(row: Tag) -> str:
    # endpoint 호출 시 국가 필터를 걸지만, 행에 country ID가 들어있으면 우선 사용
    for attr in ["data-country-id", "countryid", "data-country"]:
        value = row.get(attr)
        if value and str(value) in COUNTRY_ID_TO_KO:
            return COUNTRY_ID_TO_KO[str(value)]

    row_html = str(row).lower()
    for ko, en, cid in COUNTRY_ORDER:
        if f"country{cid}" in row_html or en in row_html:
            return ko

    # visible text 기반 fallback
    text = clean_text(row.get_text(" "))
    for ko, en, _cid in COUNTRY_ORDER:
        if en in text.lower() or ko in text:
            return ko

    return "기타"


def cell_text(row: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        el = row.select_one(selector)
        if el:
            return clean_text(el.get_text(" "))
    return "-"


def parse_events(html_table: str) -> List[EconEvent]:
    soup = BeautifulSoup(html_table, "html.parser")
    rows = soup.select("tr.js-event-item") or soup.select("tr[id^=eventRowId]")
    events: List[EconEvent] = []

    for row in rows:
        importance = count_importance(row)
        if importance < 2:
            continue

        country = extract_country(row)
        if country not in COUNTRY_RANK:
            continue

        time_text = cell_text(row, ["td.time", "td.first.left.time", "td[class*=time]"])
        event = cell_text(row, ["td.event", "td.left.event", "td[class*=event]"])
        actual = cell_text(row, ["td.act", "td[class*=act]"])
        forecast = cell_text(row, ["td.fore", "td[class*=fore]"])
        previous = cell_text(row, ["td.prev", "td[class*=prev]"])

        if event == "-":
            continue

        events.append(
            EconEvent(
                country=country,
                time=time_text,
                importance=importance,
                event=event,
                actual=actual,
                forecast=forecast,
                previous=previous,
            )
        )

    events.sort(key=lambda x: (COUNTRY_RANK.get(x.country, 999), x.time, x.event))
    return events


def build_message(events: List[EconEvent], target_date: datetime) -> str:
    date_label = target_date.strftime("%Y-%m-%d")
    lines = [f"📌 경제캘린더 주요 지표, {date_label} KST", "중요도 ★★ 이상 / 출처: Investing.com", ""]

    if not events:
        lines.append("오늘 조건에 맞는 지표가 없거나 수집에 실패했습니다.")
        return "\n".join(lines)

    for country in COUNTRY_KO_ORDER:
        country_events = [e for e in events if e.country == country]
        if not country_events:
            continue

        lines.append(f"[{country}]")
        for e in country_events:
            stars = "★" * e.importance
            lines.append(
                f"- {e.time} {stars} {e.event}\n"
                f"  실제 {e.actual} / 예상 {e.forecast} / 이전 {e.previous}"
            )
        lines.append("")

    return "\n".join(lines).strip()


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(".env에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 입력하세요.")

    # 텔레그램 메시지 길이 제한 대비 분할 전송
    chunks = []
    while len(message) > 3900:
        split_at = message.rfind("\n", 0, 3900)
        if split_at == -1:
            split_at = 3900
        chunks.append(message[:split_at])
        message = message[split_at:].lstrip()
    chunks.append(message)

    for chunk in chunks:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": chunk}, timeout=20)
        resp.raise_for_status()


def run_once() -> None:
    now_kst = datetime.now(KST)
    html_table = fetch_calendar_html(now_kst)
    events = parse_events(html_table)
    message = build_message(events, now_kst)
    send_telegram(message)
    print(f"[{now_kst:%Y-%m-%d %H:%M:%S KST}] sent {len(events)} events")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="1회만 실행하고 종료")
    args = parser.parse_args()

    if args.once:
        run_once()
        return

    run_time = os.getenv("RUN_TIME_KST", "06:00")
    try:
        hour, minute = map(int, run_time.split(":"))
    except ValueError:
        print("RUN_TIME_KST 형식은 HH:MM이어야 합니다. 예: 06:00", file=sys.stderr)
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(run_once, "cron", hour=hour, minute=minute, misfire_grace_time=600)
    print(f"Scheduler started. Daily run time: {run_time} KST")
    scheduler.start()


if __name__ == "__main__":
    main()
