# 화~토요일 06:00 KST 실행 기준

이 버전은 KST 기준 **화요일~토요일 06:00**에만 경제캘린더를 수집합니다.
일요일과 월요일에는 데이터를 가져오지 않고, 텔레그램도 발송하지 않습니다.

## 조회 구간

매 실행일 06:00 KST 기준:

- 시작: 전일 08:00 KST
- 종료: 실행 시각 06:00 KST

예시:

- 화요일 06:00 실행 → 월요일 08:00 ~ 화요일 06:00
- 수요일 06:00 실행 → 화요일 08:00 ~ 수요일 06:00
- 토요일 06:00 실행 → 금요일 08:00 ~ 토요일 06:00
- 일요일/월요일 → 실행 안 함

## .env 설정

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
RUN_TIME_KST=06:00
LOOKBACK_START_TIME_KST=08:00
RUN_WEEKDAYS_KST=tue-sat
```

## 수동 테스트

화~토가 아닌 날에 테스트 발송을 하고 싶으면 아래처럼 실행합니다.

```bat
InvestingCalendarTelegramBot.exe --once --force
```

일반 1회 실행은 요일 제한을 따릅니다.

```bat
InvestingCalendarTelegramBot.exe --once
```
