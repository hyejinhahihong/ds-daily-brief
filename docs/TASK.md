# TASK — 진행 체크리스트

> **▶ 다음 세션 시작점** (2026-07-16 기준)
> **Phase 3 코드 완성 → 사용자 발송 검증 대기(SPEC §9 3-e 멈춤 지점).**
> 디자인 v4(거터+단일컬럼, 배지 메타라인, ★ TOP3 마커) + 라우팅 사다리 v5(practice) + Phase 3 발행/발송 완료.
> **사용자가 할 일(3-e)**: ①GitHub public 레포 생성·푸시 ②Settings>Pages 브랜치 배포 켜기 ③BotFather 봇 생성
> ④Secrets(ANTHROPIC_API_KEY·TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID)+Variable(SITE_BASE_URL) 등록
> ⑤Actions에서 `daily-brief` workflow_dispatch 수동 실행 → 텔레그램 도착 확인 → 정지. (상세 안내는 세션 응답)
> **보류 결정**: 레인 5 weight(진단 완료=진짜 손실이나 며칠 운영 후 사용자 결정, DECISIONS "레인 base 분포 실측").
> **무비용 재렌더**: `uv run python -m src.run_phase2 --render-only data/written_2026-07-16.json`
> **로컬 발송 미리보기(rank+write $0.32 발생)**: `uv run python -m src.run_daily --from-json data/raw_2026-07-16.json --dry-run`

---

## Phase 0 체크리스트

> 범위: SPEC §9 Phase 0 = **수집기 7레인, 로컬 실행, 레인별 물량 실측**.
> 완료 기준: JSON 80~150건 + 레인별 물량 표.

## 구현

- [x] `pydantic` 데이터 모델 (SPEC §8 스키마, Phase 0는 수집 필드만 채움)
- [x] `config/sources.yaml` — RSS·arXiv·repo·학회 목록 + `lane_weight`/`source_tier`
- [x] 공통 유틸: URL 정규화·해시, 도메인 추출, 3일 롤링 창(§3.10), HTTP fetch
- [x] 레인 1 — 빅테크 리서치 블로그 (RSS)
- [x] 레인 2 — 학회 논문 (arXiv `comments` 정규식 파싱, §3.3-1)
- [x] 레인 3 — 큐레이션 뉴스레터 (RSS)
- [x] 레인 4 — arXiv 일반 (arXiv API + HF Daily Papers)
- [x] 레인 5 — 실무 블로그 (RSS)
- [x] 레인 6 — AI 미디어 (RSS만; 웹서치는 §10 미결정 → 제외)
- [x] 레인 7 — GitHub Releases (major/minor만, §3.8)
- [x] 레인 8 — 국문 보조 (§3.9, 선택)
- [x] 런 내 중복제거 (url_hash) + JSON 산출
- [x] 레인별 물량 표 + 피드별 진단(살아있는 RSS 판별)

## 의도적 제외 (SPEC 근거)

- Haiku 랭킹 / `base_score` / `final_score` → Phase 1 (§4.1).
  → "상위 스코어 진입률"은 이번 산출 불가. 표에 사유 명시.
- `seen.json` 영속화 → Phase 1 (§9).
- OpenReview 대조 → 베스트에포트 (핵심은 arXiv comments).
- 레인 6 웹서치 / research_house·corporate_newsroom → 웹서치 API 미결정(§10).
- 발송·HTML 렌더 → Phase 2+ (짜지 않음).

## Phase 0 보완 (2026-07-16)

- [x] 작업 1 — 죽은 피드 9개 수리: UA 폴백 사다리(정직→브라우저) 구현.
  UA로는 0개 복구(실제 URL 문제). URL 재탐색으로 3개 복구(Meta→engineering.fb.com,
  AlphaSignal→substack, Semafor→rss.xml). 6개 복구불가(대체소스 필요).
- [x] 작업 2 — arXiv 역할 분리: HF Daily=DL/LLM, arXiv raw=니치(keyword_groups).
  111→50/일 억제. keyword_groups config화. econ.EM/stat.ME 포함.
- [x] 작업 3 — 재측정: 레인별 표 + arXiv 키워드 그룹별 표.
- [x] 작업 4 — 커버리지 검증(창 2026-06-28~07-16): 레인 1/2/3 전체 목록,
  Google TabFM(2026-06-30) 레인1에서 FOUND 확인.

## Phase 0 보완 2차 (2026-07-16)

- [x] 키워드 narrowing: bare `causal`/`temporal`/`calibration` 제거. 매처 case-sensitive
  (대문자 포함 키워드 → DiD/DML/SCM/ATE/SMOTE 오탐 방지). arXiv niche 159→23.5/일(18일창).
  causal 189→99, timeseries 231→131, imbalanced 166→64.
- [x] Anthropic HTML 스크래퍼(RSS 없음 확정). 날짜=<time>, 제목=og:title. 정상 동작.
- [x] 피드 최종 정리: The Batch 확정 폐기(rss.xml=500·feed/=404). Uber/LinkedIn/DoorDash/
  LG/Semafor 제거(사유 주석). error=0 달성.
- [x] 재측정 표 + causal 변화폭 + 레인1 최종 피드 상태.

## Phase 1 (2026-07-16) — seen.json + Haiku 랭킹

- [x] SPEC v4 동기화 (레인 확정, arXiv 키워드/역할, 인과 T2 확정, §10 정리)
- [x] docs/PLAN.md 작성 (Phase 1~4, Phase 1 상세)
- [x] src/config.py — .env 로더 + 예산 가드 (SPEC §7.3)
- [x] src/dedup.py — seen.json (URL 정규화·해시, 180일, SPEC §3.11)
- [x] src/rank.py — Haiku `claude-haiku-4-5` 배치 랭킹 + 카테고리·서브태그 + `--stub`
- [x] src/select.py — final_score + 카테고리 쿼터 선별 (SPEC §2.1/§4.2)
- [x] src/run_phase1.py — 산출물 (a)(b), 3회 실행 (c) 검증
- [x] config/categories.yaml — 쿼터
- [x] **실제 Haiku 1회 실행** (2026-07-16) — $0.0725/회, 16건 선별, seen.json 297건 기록.
  진입률 표·비용 실측·Tier5 0건 → DECISIONS.md "Phase 1 실측".

## Phase 1 결정 (실행 후 확정, 2026-07-16)

- [x] `lane_weight` **전부 동결** — 진입률이 설계 의도와 일치 (DECISIONS.md).
- [x] Tier 5 **자동 판정 안 함** — 화이트리스트 유지, 페널티 로직은 보험으로 존치 (DECISIONS.md).

## 남은 결정 (Phase 2+)

- [ ] The Batch / Semafor 대체 소스
- [ ] GitHub 레인: 미인증 rate-limit → `GITHUB_TOKEN` (.env)

## Phase 2 (2026-07-16 진입) — 집필 + HTML

- [x] **docs/DESIGN.md 확정** — Airbnb 팔레트만 + 우리 규칙. 라벨 영문 통일·소스티어 비노출·굵기 하향 반영.
- [x] **abstract 수집** — Item 모델·SPEC §8에 abstract 추가. 수집기 4종(RSS/arXiv/HF/GitHub/Anthropic)이
  원문 초록/description 저장. seen.json 초기화 후 재수집(295건). 커버리지 95%(279/295 ≥100자),
  논문 165건 전량 완전초록. 티저 피드 목록 확인(research.google 19자 등, DECISIONS 참조).
- [x] src/write.py — Sonnet(`claude-sonnet-5`) 건별 집필. 근거 <100자면 엄격제한. whats_different 없으면 None.
- [x] src/render.py — 일별 HTML 1종 (index/category는 다음). DESIGN.md 토큰·레이아웃·다크토글 반영.
- [x] src/run_phase2.py — load→rank→select→write→render. `--render-only`(무비용 재렌더) + 집필 덤프.
- [x] **샘플 생성 + 육안 검토** (SPEC §9): 가독성 문제 확인 → DESIGN v2 개정.
- [x] **DESIGN.md v2** (Airbnb→Claude 팔레트, teal 액센트, 제목 액센트 제거, 배지 색 폐기,
  아코디언 도입, 목차 강화·넘버링·카테고리 설명). render.py v2 재적용. 근거 DECISIONS.md.
- [x] **샘플 재검토 3회전**: v2→v3(제목언어·bold·마스트헤드·데스크톱중앙) →v4(거터+단일컬럼·배지메타라인·★마커)
  + 라우팅 사다리 v4(양성신호 8개)→v5(practice 하단격리). DESIGN/SPEC/DECISIONS 동기화.

## Phase 3 (2026-07-16 진입) — 발행 + 발송

- [x] **3-a 데이터 영속화** — `src/publish.py`: `data/published/*.json`(SPEC §8 전문 + `schema_version`),
  `build_index`(오늘자 복사). config `SCHEMA_VERSION=5`.
- [x] **3-c 텔레그램** — `src/deliver/telegram.py`: TOP3 title_ko + 링크, fail-safe(SPEC §6.4).
- [x] **3-b 생산 러너** — `src/run_daily.py`: 수집→dedup(seen 영속화)→랭킹→선별→집필→렌더→발행→index→발송.
  `write_items(budget_remaining)` 예산 가드 추가(SPEC §7.3).
- [x] **3-d GH Actions** — `.github/workflows/daily.yml`: cron `30 21 * * 0-4` + dispatch, 커밋-백.
- [x] 신규 모듈 오프라인 검증(무비용): published 라운드트립·index 동일·텔레그램 290자·fail-safe 스킵.
- [ ] **3-e 정지 지점** ← 여기 (사용자): 레포·Pages·봇·Secrets 설정 후 workflow_dispatch → 텔레그램 도착 확인.
- [ ] (그 후) cron 자동 실행 관찰 → Phase 3.5 카카오 → Phase 4 카테고리/아카이브/RSS.
