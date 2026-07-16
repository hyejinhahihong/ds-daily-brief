# PLAN — Phase 분할 · 모듈 의존관계

> 기준은 `docs/SPEC.md`(v4). 충돌 시 SPEC이 이긴다.
> Phase 0 완료(수집기 7레인 + 실측). 이 문서는 Phase 1을 상세히, 2~4는 개요로 잡는다.

## 파이프라인 (선형)

```
collect(Phase0) → dedup/seen(Phase1) → rank/Haiku(Phase1) → select(Phase1)
   → write/Sonnet(Phase2) → render/HTML(Phase2) → deliver(Phase3+)
```

순수 Python + Anthropic SDK. 그래프 프레임워크 없음 (SPEC §1).

## 모듈 의존관계

```
src/models.py          Item 스키마 (SPEC §8) — 전 단계 공유
src/config.py          .env 로더 + 예산/호출 상한 상수 (SPEC §7.3)   [Phase1 신규]
src/collectors/*       Phase 0 (완료)
src/dedup.py           seen.json 로드/필터/갱신/프루닝 (180일)         [Phase1 신규]
src/rank.py            Haiku 필터·랭킹 (base_score/카테고리/서브태그)  [Phase1 신규]
src/select.py          final_score + 카테고리 쿼터 선별                [Phase1 신규]
src/run_phase1.py      collect→dedup→rank→select + 산출물             [Phase1 신규]
config/categories.yaml 8개 카테고리 쿼터 (SPEC §2.1)                   [Phase1 신규]
data/seen.json         중복 인덱스 (SPEC §3.11)                        [Phase1 신규]
data/preferences.md    👍👎 누적 → 랭킹 프롬프트 주입 (SPEC §4.3)       [Phase1 신규, 선택]
```

---

## Phase 1 — seen.json + Haiku 랭킹 (상세)

**완료 기준 (SPEC §9):** 같은 기사 이틀 연속 안 나옴.

### 1-1. seen.json 중복 제거 (`src/dedup.py`)
- 스키마: SPEC §3.11 (`url_hash → {url,title,category,source_tier,first_seen,tags}`).
- `load_seen()` → dict. `filter_unseen(items, seen)` → 이전 실행에서 본 url_hash 제거.
- `update_seen(seen, ranked)` → 신규 랭킹분을 `first_seen=today`로 추가(카테고리/티어/태그 포함).
- `prune(seen, days=180)` → 보존 기간 초과 제거.
- URL 정규화·해시는 `collectors/base.py`의 것 재사용 (일관성).

### 1-2. Haiku 필터·랭킹 (`src/rank.py`) — SPEC §4.1/§4.2
- 모델: **`claude-haiku-4-5`** (SPEC §4.1 지정). Anthropic SDK, `output_config.format` json_schema.
- 입력: dedup 후 신규 아이템. 배치(≈15건/콜, `max_tokens` 2000 이하 유지).
- 출력/아이템: `base_score`(0~10), `category`(8개 슬러그 1), `tags`(서브태그).
  - base_score 기준: 신규성 / 재현가능성 / **정형데이터 적용가능성** / 구체성 (SPEC §4.2).
  - 라우팅: ① causal 우선 ② DL↔예측 애매하면 예측 (SPEC §2.3).
- 프롬프트에 `preferences.md`(있으면) 주입 (SPEC §4.3, 사후 피드백).
- 예산 가드 (SPEC §7.3, 필수): `daily_call_limit=150`, `max_tokens_per_call=2000`,
  `retry_limit=3`, `daily_budget_usd=1.0` 초과 시 중단. SDK 자동 재시도 + 사용량 집계.
- `--stub`: API 없이 결정적 스코어(플럼빙 검증용). 실제 스코어는 키 필요.

### 1-3. final_score + 쿼터 선별 (`src/select.py`) — SPEC §4.2/§2.1
- `final_score = base_score × lane_weight × tier_multiplier`.
  - **lane_weight는 SPEC 현재값 그대로.** 임의 변경 금지 (Phase 1 결과 보고 후 합의).
- 카테고리별 쿼터(§2.1): T1=2 고정, T2=1~3, T3=0~2. 총 12~16, 상한 16.
- 각 카테고리 내 `final_score` 상위부터 채움. **하한 채울 후보 없으면 비운다** (SPEC 원칙 3).
- 상한 16 초과 시 전체 `final_score` 하위 컷.

### 1-4. 산출물 (`src/run_phase1.py`)
- (a) 카테고리별 선별 결과: 제목 · 레인 · source_tier · base_score · final_score.
- (b) 레인별 진입률: 레인 / 수집 / 선별 / 진입률 / 평균 base_score.
- (c) 3일 연속 실행 → seen.json이 중복을 막는지 검증.

### Phase 1 비목표 (하지 않음)
- Sonnet 집필, HTML, 발송 (Phase 2~3). lane_weight 변경. GITHUB_TOKEN 하드코딩(→ .env).

---

## Phase 2 — Sonnet 집필 + HTML (개요)
- `src/write.py`: 선별 12~16건에 요약(3~5문장) + WHY IT MATTERS + 무엇이 다른가 (SPEC §2.4). 모델 Sonnet.
- `src/render.py`: index / 일별 / 카테고리 페이지 (SPEC §5). 레퍼런스 문체 학습(§2.6).
- **§9대로 샘플 1회분 육안 확인 후 정지.** 비용 실측.

## Phase 3 / 3.5 — 발송 (개요)
- `src/deliver/telegram.py`(Phase 3) → `kakao.py`(Phase 3.5). GH Pages + Actions cron (SPEC §6·§7).
- 채널 독립, 카카오 실패 시 텔레그램 폴백. Secrets 전부 .env / GH Secrets.

## Phase 4 — 확장 (개요, 옵션)
- 카테고리 페이지 태그필터 / 주간 롤업 / RSS / 👍👎 학습 루프 / "연결된 이전 기사"(임베딩 vs 키워드).
