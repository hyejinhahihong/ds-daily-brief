# CLAUDE.md

## 프로젝트

`ds-daily-brief` — DS/AI 일간 뉴스 브리핑 자동 생성·발송.
요구사항은 **`docs/SPEC.md`가 유일한 기준**이다. 충돌 시 SPEC이 이긴다.

## 현재 Phase

**`docs/TASK.md` 상단 "▶ 다음 세션 시작점" 참조.** (현재 Phase·다음 액션은 거기서 관리 —
여기 하드코딩하면 낡는다.) Phase 정의·완료 기준은 SPEC §9.

## 작업 원칙

1. **SPEC 없으면 코드 없다. PLAN 없으면 구현 없다.**
2. **현재 Phase 밖의 코드를 쓰지 않는다.** (예: 수집 단계 요청에 발송/HTML 렌더를 짜지 말 것.)
3. 요구사항 변경 시 SPEC → PLAN → TASK 순으로 역추적 갱신.
4. 애매하면 짜지 말고 물어볼 것.

## 금지

- **LangGraph / deepagents / LangChain 도입 금지.** 순수 Python + Anthropic SDK.
  (선형 파이프라인이라 그래프 프레임워크가 불필요. SPEC §1 비목표)
- API 키·토큰 하드코딩 금지. 전부 `.env` / GH Secrets.
- 테스트 과잉 금지. 수집기 파서 단위테스트만. (SPEC §1 비목표)
- 논문·릴리스를 웹서치로 수집 금지. API로 결정적 수집. (SPEC 원칙 5)

## 스택

- Python 3.11+
- 의존성 최소화. 표준 라이브러리 우선.
- `httpx`, `feedparser`, `pydantic`, `anthropic`
- 패키지 관리: `uv`

## 디렉토리

```
docs/SPEC.md          요구사항 (유일 기준)
docs/PLAN.md          Phase 분할
docs/TASK.md          체크리스트
docs/DECISIONS.md     결정 기록 (ADR: 왜 그렇게 정했나 — 확정 결정·폐기 대안·실측)
src/collectors/       레인별 수집기 (7종)
src/rank.py           Haiku 필터·랭킹
src/write.py          Sonnet 집필
src/render.py         HTML
src/deliver/          텔레그램 / 카카오
config/sources.yaml   RSS·repo·학회 리스트
data/seen.json        중복 방지
data/preferences.md   👍👎 누적
```

## 컨벤션

- 코드·주석·변수명: 영어
- 커밋 메시지·문서·산출물: 한국어
- 커밋: `feat(collector): arXiv 레인 추가` 형식
- 데이터 모델은 `pydantic.BaseModel`. SPEC §8 스키마를 그대로 따를 것.

## 자주 하는 실수

- `lane_weight` 값을 임의로 바꾸지 말 것. Phase 0 실측 후 사용자와 합의해 조정.
- 카테고리 쿼터를 억지로 채우지 말 것. 후보 없으면 비운다. (SPEC 원칙 3)
- 소스 판정을 "벤더냐"로 하지 말 것. "원 소스냐"로 한다. (SPEC 원칙 7)