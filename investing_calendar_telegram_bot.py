"""
Investing.com Economic Calendar -> Telegram
- KST 기준 화~토 06:00 실행 가능
- 조회 구간: 전일 08:00 KST ~ 실행 시각 KST
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
from datetime import datetime, time, timedelta
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

# Python weekday: 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
# 사용자가 요청한 수집일: KST 기준 화~토
DEFAULT_RUN_WEEKDAYS = {1, 2, 3, 4, 5}
WEEKDAY_ALIASES = {
    "mon": 0, "monday": 0, "월": 0, "월요일": 0,
    "tue": 1, "tues": 1, "tuesday": 1, "화": 1, "화요일": 1,
    "wed": 2, "wednesday": 2, "수": 2, "수요일": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "목": 3, "목요일": 3,
    "fri": 4, "friday": 4, "금": 4, "금요일": 4,
    "sat": 5, "saturday": 5, "토": 5, "토요일": 5,
    "sun": 6, "sunday": 6, "일": 6, "일요일": 6,
}


@dataclass
class EconEvent:
    country: str
    dt_kst: Optional[datetime]
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


def parse_hhmm(value: str, default: str) -> tuple[int, int]:
    raw = (value or default).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if not match:
        raw = default
        match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"시간 형식이 올바르지 않습니다: {value}")
    return hour, minute


def parse_run_weekdays(value: str | None = None) -> set[int]:
    """.env의 RUN_WEEKDAYS_KST를 파싱. 기본값은 화~토."""
    raw = (value or os.getenv("RUN_WEEKDAYS_KST", "tue-sat")).strip().lower()
    if not raw:
        return set(DEFAULT_RUN_WEEKDAYS)

    if raw in {"tue-sat", "tuesday-saturday", "화-토", "화요일-토요일"}:
        return set(DEFAULT_RUN_WEEKDAYS)

    result: set[int] = set()
    for part in re.split(r"[,/ ]+", raw):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_raw, end_raw = [x.strip() for x in part.split("-", 1)]
            if start_raw not in WEEKDAY_ALIASES or end_raw not in WEEKDAY_ALIASES:
                raise ValueError(f"RUN_WEEKDAYS_KST 요일 형식이 올바르지 않습니다: {part}")
            start, end = WEEKDAY_ALIASES[start_raw], WEEKDAY_ALIASES[end_raw]
            if start <= end:
                result.update(range(start, end + 1))
            else:
                result.update(range(start, 7))
                result.update(range(0, end + 1))
        else:
            if part not in WEEKDAY_ALIASES:
                raise ValueError(f"RUN_WEEKDAYS_KST 요일 형식이 올바르지 않습니다: {part}")
            result.add(WEEKDAY_ALIASES[part])
    return result or set(DEFAULT_RUN_WEEKDAYS)


def should_collect_today(now_kst: Optional[datetime] = None) -> bool:
    now_kst = now_kst or datetime.now(KST)
    if now_kst.tzinfo is None:
        now_kst = KST.localize(now_kst)
    else:
        now_kst = now_kst.astimezone(KST)
    return now_kst.weekday() in parse_run_weekdays()


def get_collection_window(now_kst: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """기본 조회 구간: 전일 08:00 KST ~ 실행 시각 KST."""
    now_kst = now_kst or datetime.now(KST)
    if now_kst.tzinfo is None:
        now_kst = KST.localize(now_kst)
    else:
        now_kst = now_kst.astimezone(KST)

    lookback_time = os.getenv("LOOKBACK_START_TIME_KST", "08:00")
    start_hour, start_minute = parse_hhmm(lookback_time, "08:00")

    start_date = (now_kst - timedelta(days=1)).date()
    start_dt = KST.localize(datetime.combine(start_date, time(start_hour, start_minute)))
    end_dt = now_kst
    return start_dt, end_dt


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


def fetch_calendar_html(start_dt: datetime, end_dt: datetime) -> str:
    session = get_browser_session()
    date_from = start_dt.strftime("%Y-%m-%d")
    date_to = end_dt.strftime("%Y-%m-%d")
    country_ids = [cid for _ko, _en, cid in COUNTRY_ORDER]

    # 중요도 2, 3만 요청. 일부 시점에서 서버가 이 필터를 무시할 수 있어 파싱 후에도 재필터링함.
    # dateFrom/dateTo는 날짜 단위라서, 실제 전일 08:00~현재 시각 필터는 parse 단계에서 한 번 더 적용함.
    data = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "timeZone": "88",  # Asia/Seoul로 알려진 값. 미작동 시 페이지 시간대와 대조 필요.
        "timeFilter": "timeOnly",
        "currentTab": "custom",
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
    row_html = str(row)

    count = row_html.count("grayFullBullishIcon") + row_html.count("bullishIcon")
    if count > 0:
        return min(count, 3)

    match = re.search(r"bull(\d)", row_html, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return 0


def extract_country(row: Tag) -> str:
    for attr in ["data-country-id", "countryid", "data-country"]:
        value = row.get(attr)
        if value and str(value) in COUNTRY_ID_TO_KO:
            return COUNTRY_ID_TO_KO[str(value)]

    row_html = str(row).lower()
    for ko, en, cid in COUNTRY_ORDER:
        if f"country{cid}" in row_html or en in row_html:
            return ko

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


def parse_event_datetime_from_attrs(row: Tag) -> Optional[datetime]:
    """Investing.com 행의 data-event-datetime류 속성에서 KST datetime을 추출."""
    attr_candidates = [
        "data-event-datetime",
        "data-event-datetime-local",
        "event-datetime",
        "data-event-date",
    ]
    for attr in attr_candidates:
        value = row.get(attr)
        if not value:
            continue
        parsed = parse_datetime_string(str(value))
        if parsed:
            return parsed

    # data-event-timestamp가 초 단위 Unix timestamp인 변형 대비
    for attr in ["data-event-timestamp", "event_timestamp", "data-timestamp"]:
        value = row.get(attr)
        if not value:
            continue
        try:
            ts = int(str(value))
            if ts > 10_000_000_000:  # ms 단위면 초 단위로 변환
                ts //= 1000
            return datetime.fromtimestamp(ts, tz=KST)
        except Exception:
            pass

    return None


def parse_datetime_string(value: str) -> Optional[datetime]:
    value = clean_text(value)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return KST.localize(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


def infer_event_datetime_from_time(time_text: str, start_dt: datetime, end_dt: datetime) -> Optional[datetime]:
    """
    속성에 날짜가 없을 때 fallback.
    전일 08:00~오늘 06:00 같은 24시간 미만 구간을 전제로,
    HH:MM이 시작시각 이상이면 전일, 종료시각 이하면 오늘로 추정.
    """
    match = re.search(r"(\d{1,2}):(\d{2})", time_text or "")
    if not match:
        return None

    hour, minute = int(match.group(1)), int(match.group(2))
    start_candidate = KST.localize(datetime.combine(start_dt.date(), time(hour, minute)))
    end_candidate = KST.localize(datetime.combine(end_dt.date(), time(hour, minute)))

    candidates = [start_candidate, end_candidate]
    in_window = [dt for dt in candidates if start_dt <= dt <= end_dt]
    if in_window:
        return in_window[0]
    return None


def parse_events(html_table: str, start_dt: datetime, end_dt: datetime) -> List[EconEvent]:
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
        event_dt = parse_event_datetime_from_attrs(row) or infer_event_datetime_from_time(time_text, start_dt, end_dt)
        if event_dt is None or not (start_dt <= event_dt <= end_dt):
            continue

        event = cell_text(row, ["td.event", "td.left.event", "td[class*=event]"])
        actual = cell_text(row, ["td.act", "td[class*=act]"])
        forecast = cell_text(row, ["td.fore", "td[class*=fore]"])
        previous = cell_text(row, ["td.prev", "td[class*=prev]"])

        if event == "-":
            continue

        events.append(
            EconEvent(
                country=country,
                dt_kst=event_dt,
                time=event_dt.strftime("%m-%d %H:%M"),
                importance=importance,
                event=event,
                actual=actual,
                forecast=forecast,
                previous=previous,
            )
        )

    events.sort(key=lambda x: (COUNTRY_RANK.get(x.country, 999), x.dt_kst or end_dt, x.event))
    return events


def build_message(events: List[EconEvent], start_dt: datetime, end_dt: datetime) -> str:
    range_label = f"{start_dt:%Y-%m-%d %H:%M}~{end_dt:%Y-%m-%d %H:%M} KST"
    lines = [f"📌 경제캘린더 주요 지표", range_label, "중요도 ★★ 이상 / 출처: Investing.com", ""]

    if not events:
        lines.append("조건에 맞는 지표가 없거나 수집에 실패했습니다.")
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


def run_once(force: bool = False) -> None:
    now_kst = datetime.now(KST)
    if not force and not should_collect_today(now_kst):
        print(f"[{now_kst:%Y-%m-%d %H:%M:%S KST}] skipped: collection days are KST Tue-Sat only")
        return

    start_dt, end_dt = get_collection_window(now_kst)
    html_table = fetch_calendar_html(start_dt, end_dt)
    events = parse_events(html_table, start_dt, end_dt)
    message = build_message(events, start_dt, end_dt)
    send_telegram(message)
    print(f"[{now_kst:%Y-%m-%d %H:%M:%S KST}] sent {len(events)} events / range {start_dt:%Y-%m-%d %H:%M}~{end_dt:%Y-%m-%d %H:%M}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="1회만 실행하고 종료")
    parser.add_argument("--force", action="store_true", help="요일 제한을 무시하고 테스트 실행")
    args = parser.parse_args()

    if args.once:
        run_once(force=args.force)
        return

    run_time = os.getenv("RUN_TIME_KST", "06:00")
    try:
        hour, minute = parse_hhmm(run_time, "06:00")
    except ValueError:
        print("RUN_TIME_KST 형식은 HH:MM이어야 합니다. 예: 06:00", file=sys.stderr)
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(run_once, "cron", day_of_week="tue-sat", hour=hour, minute=minute, misfire_grace_time=600)
    print(f"Scheduler started. Run days: Tue-Sat / Run time: {run_time} KST")
    scheduler.start()


if __name__ == "__main__":
    main()
