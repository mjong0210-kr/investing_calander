# .env 로딩 방식 안내

v4부터 프로그램은 현재 작업 폴더가 아니라 **EXE가 있는 폴더**에서 `.env`를 읽습니다.

정상 구조:

```text
C:\InvestingCalendarBot\
├─ InvestingCalendarTelegramBot.exe
└─ .env
```

실행하면 콘솔에 아래처럼 표시됩니다.

```text
Loaded .env: C:\InvestingCalendarBot\.env / exists=True
Scheduler started. Run days: Tue-Sat / Run time: 07:00 KST
```

`exists=False`가 뜨면 `.env` 파일이 EXE와 같은 폴더에 없거나, 실제 파일명이 `.env.txt`일 가능성이 큽니다.

Windows에서 확인:

1. 파일 탐색기 → 보기 → 표시 → 파일 확장명 체크
2. 파일명이 `.env.txt`가 아니라 정확히 `.env`인지 확인

예시 `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
RUN_TIME_KST=07:00
LOOKBACK_START_TIME_KST=08:00
RUN_WEEKDAYS_KST=tue-sat
```
