# Investing.com Economic Calendar Telegram Bot

매일 KST 06:00에 Investing.com 경제캘린더에서 중요도 2 이상 지표를 가져와 텔레그램으로 보냅니다.

## 설치
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
playwright install chromium
```

## 설정
`.env.example`을 `.env`로 복사한 뒤 텔레그램 봇 토큰과 chat_id를 입력하세요.

## 실행
```bash
python investing_calendar_telegram_bot.py
```

테스트 1회 발송:
```bash
python investing_calendar_telegram_bot.py --once
```

## Windows 작업 스케줄러 추천
이 스크립트 자체에 스케줄러가 들어있지만, PC 재부팅/절전 문제를 고려하면 Windows 작업 스케줄러에서 매일 06:00에 `python investing_calendar_telegram_bot.py --once`를 실행하도록 등록하는 방식이 더 안정적입니다.
