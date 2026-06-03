# Windows EXE로 쓰는 방법

## 결론
이 Python 스크립트는 `.exe`로 패키징하면 Python을 설치하지 않은 PC에서도 실행할 수 있습니다.
다만 Windows용 EXE는 Windows 환경에서 빌드해야 하므로, 아래 둘 중 하나를 사용하세요.

## 방법 A: 다른 Windows PC에서 빌드
1. Python이 설치된 Windows PC에서 이 폴더를 엽니다.
2. `build_windows_exe.bat`를 실행합니다.
3. 빌드가 끝나면 `dist\InvestingCalendarTelegramBot.exe`가 생성됩니다.
4. 이 EXE와 `.env` 파일을 사용자 PC의 같은 폴더에 둡니다.
5. EXE를 더블클릭하거나 Windows 작업 스케줄러에 등록합니다.

## 방법 B: GitHub Actions로 빌드하기, 내 PC에 Python 설치 불필요
1. GitHub에서 새 private repository를 만듭니다.
2. 이 폴더의 모든 파일을 업로드합니다. `.github/workflows/build-windows-exe.yml`도 포함해야 합니다.
3. GitHub 상단 `Actions` 탭으로 이동합니다.
4. `Build Windows EXE` 워크플로를 선택합니다.
5. `Run workflow`를 누릅니다.
6. 완료 후 Artifacts에서 `InvestingCalendarTelegramBot-windows`를 다운로드합니다.
7. 압축을 풀면 `InvestingCalendarTelegramBot.exe`가 있습니다.

## 실행 전 설정
EXE와 같은 폴더에 `.env` 파일을 둡니다.

```env
TELEGRAM_BOT_TOKEN=너의_텔레그램_봇_토큰
TELEGRAM_CHAT_ID=너의_채팅_ID
RUN_TIME_KST=06:00
```

## 테스트 실행
명령 프롬프트에서:

```bat
InvestingCalendarTelegramBot.exe --once
```

## 매일 06:00 자동 실행
Windows 작업 스케줄러에서 새 작업을 만들고 실행 파일을 아래처럼 지정하세요.

- 프로그램: `C:\경로\InvestingCalendarTelegramBot.exe`
- 인수: `--once`
- 시작 위치: EXE와 `.env`가 들어있는 폴더

작업 스케줄러를 쓰면 EXE를 계속 켜둘 필요가 없습니다.
