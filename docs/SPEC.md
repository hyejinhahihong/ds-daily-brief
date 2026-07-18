# SPEC — DS Daily Brief (v2)

데이터사이언티스트 개인용 일간 뉴스 브리핑 자동 생성·발송 시스템

- 프로젝트명: `ds-daily-brief`
- 버전: **v6 (진행 중, Phase 4 커버리지 개선 — 2026-07-18~)**. v5 대비: 회귀 하네스(§12) 신설,
  이후 작업에서 수집 리콜(웹서치)·스코어 축 분리·곱셈→가산·이벤트 중요도 축 반영 예정.
- 버전: v4 (2026-07-16)
- v3 대비 변경: **Phase 0 실측 반영.** 레인 1/3/6 피드 확정(죽은 소스 제거), arXiv 역할 분리·키워드 그룹 확정, 인과추론 T2 확정, §10 미결정 정리.
- v2 대비 변경: **뉴스/미디어 레인 복원(v2 누락 버그)** / 소스 티어 재정의(원본성 축) / 레인·티어 2축 분리

---

## 1. 목적

데이터사이언스(방법론 축)와 AI 산업(트렌드 축)을 매일 아침 **10분 안에** 훑을 수 있는
브리핑을 자동 생성하고, 날짜별 URL로 아카이빙하며, 메신저로 발송한다.

**목적 우선순위**
1. 결과물(뉴스레터) 확보 — 빠르게
2. 트렌드 파악 / 학습

**비목표 (Out of Scope)**
- 대외 발행·구독자 관리 (본인 1인용)
- LangGraph/deepagents 등 에이전트 프레임워크 학습 → **순수 Python + Claude API**
- 63개 테스트 풀세트 TDD → 수집기 파서 단위테스트만
- 개인 과제(VOC/NPS/RAG) 매핑 → **v2에서 제외.** preferences.md 누적 후 재검토

---

## 2. 콘텐츠 정의

### 2.1 카테고리 (8개, 고정)

| # | 카테고리 | 티어 | 일 건수 |
|---|---|---|---|
| 1 | AI Agent | T1 | 2 |
| 2 | LLM / Foundation Model | T1 | 2 |
| 3 | Deep Learning | T2 | 1~3 |
| 4 | 예측 모델링 | T2 | 1~3 |
| 5 | **인과추론** | **T2 (확정)** | **1~3** |
| 6 | MLOps / ML Engineering | T1 | 2 |
| 7 | **실무 사례 · 노하우** | **T2 (v5 승격)** | **1~3** |
| 8 | 산업 적용 사례 | T1 | 2 |

> **id: `practice`** (구 `fde`). 경로 `/category/practice.html`.
> **정의**: AI/ML 실무자의 작업 방식·워크플로·시행착오·회고·팁, Forward Deployed Engineer 사례,
> 기업 현장 구축 사례. **방법론 연구나 제품 발표가 아니라 "어떻게 일하나"를 다루는 글.**
> 섹션 설명 1줄: `실무자의 작업 방식·회고·팁 — FDE 사례, 현장 구축, 시행착오`

**총 12~16건 / 일** (상한 16건, 초과 시 스코어 하위 컷)

- T1: 매일 2건 고정. 물량 충분.
- T2: 1~3건 가변.
- T3: 0건 허용. 없으면 `금일 신규 없음 · 최근 7일 N건 ▸` 로 접어서 표시.
  빈 섹션은 결함이 아니라 "그 분야가 조용하다"는 신호로 취급한다.

> **v1→v2**: 인과추론 T3→T2 승격. causal-* 콘텐츠를 전량 흡수하므로 물량 증가 예상.
> **v4 확정**: Phase 0 실측으로 T2 유지 확정. 근거 — arXiv raw causal 5.5/일(18일창) + 학회 causal 0.56/일.
> T2 하한(1~3건)을 채우고도 남는 물량이라 승격이 타당함. (bare "causal" 오탐 제거 후 수치, §3.5)
> **v5 확정**: `fde` → `practice`(실무 사례·노하우)로 확장·개명 + T3→T2 승격. 근거 — 구 FDE는 정의가 좁아
> Phase 1 실측 0건, 실무자 회고·워크플로·팁이 갈 곳 없어 기본값(예측 모델링)으로 떨어졌다. 정의를 "어떻게
> 일하나"로 넓히면 레인 5(실무 블로그) 25건/일이 주 공급원이 되어 물량이 붙는다. 실측은 재실행으로 재확인.
> (T3 소멸 — 현재 T3 카테고리 없음. 아래 T3 설명은 빈 섹션 처리 방식 참고용으로 유지.)

### 2.2 서브태그

**예측 모델링**
`#tabular` `#XAI` `#anomaly` `#timeseries` `#imbalanced` `#clustering` `#feature-selection`

**인과추론**
`#did` `#psm-ipw` `#uplift` `#double-ml` `#causal-forest` `#causal-discovery` `#causal-llm`

> **v1→v2**: `#causal-ml` 태그 삭제. causal 관련은 전부 카테고리 5로 라우팅.

### 2.3 라우팅 규칙 — 우선순위 사다리 (v4 전면 개정)

> **v3→v4 개정 근거.** 구 규칙은 2개뿐이라 **8개 중 3개(인과·DL·예측)만** 다뤘다. 나머지 5개
> (agent·llm-fm·mlops·fde·industry)에 양성 신호가 없어 "애매하면 → 예측 모델링" 기본값이 **자석**이
> 됐다(증거: 재검토 전 TOP 3 중 2개가 예측 모델링, Meta 광고 최적화 논문까지 흡수). → 8개 전부에
> 양성 신호를 주는 **우선순위 사다리**로 재작성. 근거 DECISIONS.md.

> **v5 재배치 근거.** 다른 7개는 **주제**로 나뉘고(무엇에 관한 글인가), `practice`(실무 사례·노하우)만
> **형식**으로 나뉜다(어떻게 쓰인 글인가). 예: "Airbnb가 LLM 평가를 하루로 단축한 회고"는 MLOps 주제이면서
> 노하우 형식이다. **형식 축을 사다리 위에 두면 실무 글을 전부 흡수해** 예측 모델링이 자석이던 문제가 재발한다.
> → `practice`를 **사다리 맨 아래(rung 8)**로 내려, 주제 rung(1~7)에서 갈 곳이 없는 형식-글만 담게 한다.

**위에서부터 순서대로 판정하고 첫 매치에서 확정한다.**

1. **인과추론** — causal inference / treatment effect / counterfactual / confounder / uplift /
   DiD / propensity / double ML / causal discovery / SCM. (딥러닝이든 tabular든 무관 — 기존 causal-우선 유지)
2. **AI Agent** — 자율 실행 / 툴 사용 / 함수 호출(function calling) / 멀티에이전트 / 오케스트레이션 / MCP / 에이전틱 워크플로
3. **LLM / Foundation Model** — 모델 출시·학습·벤치마크 / RAG / 프롬프트 / 정렬(alignment) / LLM 평가·신뢰도 / 컨텍스트
4. **MLOps / ML Engineering** — 파이프라인 / 서빙 / 배포 / 모니터링 / 드리프트 / 피처 스토어 / 레지스트리 / 실험 추적
5. **산업 적용 사례** — 특정 기업·산업의 실제 도입 사례 / 도입률·ROI 조사 / 추천·광고·검색 등 서비스 적용
   (연구 자체가 아니라 **적용**이 주제일 때)
6. **Deep Learning** — 아키텍처·학습기법 **자체**가 주제
7. **예측 모델링** — 예측 **태스크 적용**이 주제 (tabular / 시계열 / 이상탐지 / 불균형 / 클러스터링 / XAI)
8. **실무 사례 · 노하우 (`practice`)** — 실무자의 작업 방식·워크플로·시행착오·회고·팁 / FDE 사례 / 현장 구축.
   **"어떻게 일하나"가 주제이고 rung 1~7 어디에도 안 걸릴 때만.**

**기본값**: 주제가 잡히면 해당 rung, 아무것도 안 걸리면 **7번(예측 모델링)**.

**추가 판정 원칙 (Haiku 프롬프트에 반드시 명시):**
- **표면 키워드가 아니라 주제로 판단한다.**
  예: `Uncertainty Quantification for LLM Function-Calling`은 UQ가 표면 신호지만 주제는 LLM 함수 호출
  → 2번(AI Agent) 또는 3번(LLM/FM). **예측 모델링 아님.**
- **주제가 명확하면 주제 rung으로 간다. 주제가 없을 때만 8번(실무).**
  예: "Airbnb, LLM 평가 파이프라인 4계층 구축 회고" → 주제가 MLOps → **rung 4**.
      "Anthropic 엔지니어가 Claude Code로 일하는 법" → 주제 rung 어디에도 안 걸림 → **rung 8**.
- **8번은 "실무 글이니까 여기"가 아니라 "주제 rung에서 갈 곳이 없을 때"만이다.**
- 주제도 형식도 안 걸리는 최종 기본값은 **7번(예측 모델링)**. 기본값 의존 배정은 `routed_by_default` 플래그로
  로그에 표시한다. 8번(실무)이 과다하면 형식 축이 자석이 된 것이므로 경고·검토한다.

### 2.4 아이템 포맷

```
[배지] 제목 (원문 링크)
출처 도메인 · 소스 티어

요약 3~5문장 (한국어, 원문 언어 무관)

WHY IT MATTERS
왜 중요한가 — 맥락·함의. 1~2문장. 사실 재진술 금지.

WHAT'S DIFFERENT
기존 방식 대비 차이. 1~2문장.
비교 대상을 반드시 명시할 것 (예: "기존 DoWhy의 백도어 조정 대비~").
비교 대상이 없으면 이 슬롯 생략.

↳ 연결된 이전 기사: (있을 때만)
```

**배지**: `📰 뉴스` `📄 논문` `📦 릴리스` `✍️ 블로그`

> **v1→v2**: 해석 슬롯을 카테고리별로 분기하지 않는다. **전 아이템 공통 2슬롯.**
> "적용 가능성(개인 과제 매핑)" 삭제 — 억지 매핑을 유발하고, 학습·트렌드 목적과 상충.

**제목 언어 — content_type별 분기 (v4, `title_ko` 필드 §8).**
- **📄 paper**: 원문 제목이 주 제목(학술 검색 키라 번역 금지). `title_ko`(한글 한 줄 요약)는 부제로 작게.
- **📰 news / ✍️ blog / 📦 release**: `title_ko`(한글 재작성)가 주 제목. 원문 제목은 부제로 작게.
- `title_ko` 작성: 직역 금지, 정보 담은 재작성(수치·고유명사·결론 포함), 40~60자, 고유명사는 원문 표기 유지.

**본문 강조 — bold만 (v4).**
- summary / why_it_matters / whats_different 안에서 핵심 구절만 강조. **문단당 최대 2개**(0개 허용).
- 대상: 수치·결론·핵심 고유명사. 굵기 600, 색은 본문색 유지.
- **형광펜(배경 하이라이트) 금지. 제목·강조에 액센트 색 금지.** (읽기물이 시끄러워진다 — DESIGN §3/§8)

### 2.5 상단 다이제스트

`TODAY'S TOP 3` — 전체에서 3건 선정, 각 1줄.
카카오·텔레그램 발송 본문으로 재사용.

### 2.6 톤앤매너

레퍼런스: `https://salighten.github.io/it-news/news/2026/07/02.html`
구현 시 이 URL을 분석해 문체·문장 길이·구조를 학습시킬 것.

---

## 3. 수집

### 3.1 레인 (7종)

**두 개의 독립 축으로 평가한다. 혼동 금지.**

| 축 | 의미 | 값 |
|---|---|---|
| `lane_weight` | **관심도** — 사용자가 얼마나 보고 싶은가 | 0.4 ~ 1.0 |
| `source_tier` | **원본성** — 발표 주체 본인인가, 2차 가공인가 | 1 ~ 5 |

> 두 축은 독립이다. 예: GitHub 릴리스는 발표 주체 본인이므로 `source_tier=1`이지만,
> 대부분 버그픽스라 관심도가 낮아 `lane_weight=0.4`. 반대로 미디어 기사는
> `source_tier=4`여도 큰 이슈면 관심도가 있다.

| # | 레인 | lane_weight | 방식 | 주 공급 대상 |
|---|---|---|---|---|
| **1** | 빅테크 리서치 블로그 | **1.0** | RSS | 전 카테고리 |
| **2** | 학회 논문 | **0.85** | arXiv `comments` 파싱 + OpenReview API | DL, 예측, 인과 |
| **3** | 큐레이션 뉴스레터 | **0.8** | RSS | 전 카테고리 |
| **4** | arXiv 일반 | **0.7** | arXiv API + HF Daily Papers | DL, 예측, 인과 |
| **5** | 실무 블로그 | **0.6** | RSS | DL, 예측, MLOps |
| **6** | AI 미디어 | **0.55** | RSS + 웹서치 | Agent, LLM/FM, 산업적용 |
| **7** | GitHub Releases | **0.4** | GitHub API, 메이저만 | 예측, 인과, MLOps |
| **9** | 모델 릴리스 | **0.8** | HuggingFace Hub API, org 화이트리스트+임계치 | LLM/FM, 예측(tabular/timeseries FM) |

*(+ 국문 보조 레인 — §3.9)*

> **레인 번호 ≠ 우선순위.** 우선순위는 `lane_weight` 가 유일하게 정한다(레인 1=1.0 최상, 레인 7=0.4 최하).
> 레인 9(모델 릴리스, 0.8)가 8(국문 보조, 0.6)보다 뒷번호지만 우선순위는 더 높다 — 번호는 등록 순서일 뿐.
> **번호 정렬을 위한 재번호는 하지 않는다**(config·코드 다수 참조 + seen.json lane 값 의미 흔들림, Phase 4 작업 2).
> 레인 8·9 는 §3.1 표에 정식 등재되나, 레인 7 이 마지막 "주 레인"이라 관용적으로 "7종"으로 부른다.

**커뮤니티(HN / r/MachineLearning)는 제외.**

> **설계 근거**
> - 논문·릴리스를 LLM 웹서치에 맡기면 최신성이 무너진다 → API로 결정적 수집.
> - 학회 논문은 연 1회 몰리지만, **저자가 arXiv `comments`에 "Accepted at NeurIPS 2026"을 적는다.**
>   이를 파싱하면 학회 시즌을 기다리지 않고 연중 상시 포착 가능.
> - 큐레이션 뉴스레터는 이미 사람이 거른 결과물 → 필터 입력 품질을 공짜로 올린다.
> - `lane_weight`는 **Phase 0 실측 후 튜닝 대상.** 현재 값은 추정치.

### 3.1.1 소스 티어 (원본성 축)

레퍼런스 뉴스레터 분석 결과, 품질 문제는 "벤더냐 아니냐"가 아니라
**"원 소스냐 2차 가공이냐"**였다. 벤더 배제는 잘못된 축이다.

| Tier | 정의 | 배수 | 예 |
|---|---|---|---|
| **1** | **원 소스** — 발표 주체 본인, 데이터 생산자 | 1.0 | 빅테크 리서치 블로그, arXiv, 학회, 벤더 공식 발표(`devblogs.microsoft.com`), 자체 조사 리포트(Deloitte/Gartner/IDC), 벤치마크 운영자(`vellum.ai`), GitHub Releases |
| **2** | **큐레이션** — 사람이 이미 거른 것 | 0.95 | Import AI, The Batch, HF Blog, O'Reilly Radar |
| **3** | **실무 블로그** | 0.85 | TDS, KDnuggets, ML Mastery, 개인 블로그 |
| **4** | **미디어** | 0.8 | TechCrunch, VentureBeat, MIT Tech Review, 업계지 |
| **5** | **2차 가공** — SEO성 요약, 기고형 PR | **0.5 (페널티)** | 남의 벤치마크 재편집, 콘텐츠 마케팅 백서 |

**Tier 5는 배제가 아니라 페널티다.** 그날 다른 게 없으면 올라올 수 있다.
가변 쿼터(§2.1)를 채택했으므로 억지로 채울 의무가 없고, 페널티만으로 자연 도태된다.

> **판정 기준**: "이 매체가 이 정보를 **생산**했는가, **재포장**했는가"
> - `devblogs.microsoft.com`이 자사 프레임워크 발표 → Tier 1 (벤더지만 원 소스)
> - `techsy.io`가 남의 LLM 벤치마크를 모아 정리 → Tier 5 (비벤더지만 2차 가공)

### 3.2 레인 1 — 빅테크 리서치 블로그 (RSS)

**Phase 0 실측으로 살아있는 피드 10개 확정** (config/sources.yaml 기준):

```yaml
frontier_research:
  - Google Research Blog            # research.google/blog/rss/
  - Google DeepMind Blog            # deepmind.google/blog/rss.xml
  - Microsoft Research Blog         # microsoft.com/en-us/research/feed/
  - Apple ML Research               # machinelearning.apple.com/rss.xml
  - NVIDIA Developer Blog           # developer.nvidia.com/blog/feed
  - OpenAI News                     # openai.com/news/rss.xml
  - Anthropic News                  # RSS 없음 → HTML 스크래퍼 (collectors/anthropic_news.py)
  - Meta Engineering                # engineering.fb.com/feed/ (ai.meta.com RSS 404)
  # 창 내 신규 없어 실측 0건이나 피드는 살아있음 → 유지:
  - Amazon Science Blog             # amazon.science/index.rss
  - Spotify Engineering             # engineering.atspotify.com/feed/

applied_engineering:   # tabular 실무 사례
  - Netflix Tech Blog               # netflixtechblog.com/feed
  - Airbnb Engineering              # medium.com/feed/airbnb-engineering
```

**제거 (RSS 폐지/미제공, Phase 0 확인):**
- Uber Engineering — eng 블로그 RSS 폐지 (uber.com 406, eng.uber.com 404)
- LinkedIn Engineering — RSS 폐지 (전 경로 404)
- DoorDash Engineering — 403 Cloudflare, Medium 핸들 빈 피드
- (Anthropic은 공식 RSS 없으나 HTML 스크래퍼로 복원 — 위 목록 유지)

### 3.3 레인 2 — 학회 논문

**추적 학회**
```yaml
general_ml:
  - NeurIPS, ICML, ICLR, AISTATS, AAAI, UAI
data_mining_web:
  - KDD, CIKM, WWW, WSDM, RecSys
causal:
  - CLeaR, ACIC, "Causal Learning and Reasoning"
```

**수집 방법**
1. arXiv API의 `comments` 필드를 정규식 파싱
   - 패턴: `Accepted (at|to|by) <학회명> (20\d\d)`, `<학회명> 20\d\d`, `camera-ready` 등
2. OpenReview API — ICLR/NeurIPS accepted 목록 대조
3. 매칭 시 랭킹 스코어 가점 + 배지에 학회명 표기

**한계 (2026-07-18 실측, Phase 4 작업 1).** 현 레인 2는 **arXiv comment 의 venue 파싱뿐**이라
"이 논문이 어느 학회에 수락됐나"만 잡는다. **학회 자체 이벤트(수상작 발표·제출 통계·키노트)는
구조적으로 못 잡는다.** 실측: 2026-07-16 raw(295건)에 `ICML 2026` 문자열이 9건 있었으나 전부
수락-논문 venue 태그였고, ICML 2026 어워드 발표(원 소스 `blog.icml.cc/2026/07/05/...`)는 0건.
→ **레인 2에 학회 공식 채널 추가(작업 2 완료).** `lane2_official_feeds`(RSS, lane=2·weight 0.85·tier 1,
   `content_type: news` 오버라이드). 진단 결과: **blog.icml.cc / blog.neurips.cc / blog.iclr.cc 채택**
   (icml 피드 첫 항목이 정확히 "Announcing the ICML 2026 Awards"), **KDD 제외**(kdd.org/feed 404).
   원 소스는 피드가 잡아야 한다 — 웹서치는 2차 매체만 데려온다(작업 6 설계 근거).

### 3.4 레인 3 — 큐레이션 뉴스레터 (RSS)

이미 사람이 거른 결과물. 우리 필터의 입력 품질을 올린다.

```yaml
curated:
  - Import AI (Jack Clark)          # importai.substack.com/feed
  - Last Week in AI                 # lastweekin.ai/feed
  - TLDR AI                         # tldr.tech/api/rss/ai
  - AlphaSignal                     # alphasignalai.substack.com/feed (alphasignal.ai/rss 404)
  - Hugging Face Blog               # huggingface.co/blog/feed.xml (tier 1)
  - O'Reilly Radar                  # oreilly.com/radar/feed/index.xml
```

**제거 (Phase 0 확인):**
- The Batch — 작동 피드 없음 (rss.xml=500, feed/=404). 대체 소스 확보 시 복원.

### 3.5 레인 4 — arXiv 일반

- 카테고리: `cs.LG`, `stat.ML`, `cs.AI`, `econ.EM`(인과), `stat.ME`(인과)
- 페이징: `submittedDate` 내림차순으로 수집 창 컷오프까지 (단일 요청 300건 상한이 3일 창도 잘라먹음 → 페이징 필수)

**역할 분리 (Phase 0 확정):** HF Daily Papers는 LLM 편향이 커 DL/LLM·FM을 담당하고,
arXiv raw는 HF가 안 다루는 니치만 전담 → firehose 억제.
- **HF Daily Papers** → 통과(큐레이션됨). DL / LLM·FM 스트림.
- **arXiv raw** → 아래 `keyword_groups`에 매칭되는 논문만 통과. 나머지 드롭.
- **arXiv `comments`에 학회 표기** → 레인 2로 라우팅(키워드 무관 전량 유지, §3.3).

**키워드 그룹 확정본** (config/sources.yaml `arxiv.keyword_groups`):
`causal` `tabular` `xai` `timeseries` `anomaly` `imbalanced` `clustering` (SPEC §2.2 서브태그와 대응)

- **대소문자 매칭 규칙**: 대문자가 포함된 키워드는 **대소문자 구분(case-sensitive)** 매칭한다.
  이유: `DiD`(difference-in-differences)를 대소문자 무시로 매칭하면 흔한 단어 "did"를 전부 잡아
  causal이 폭증한다. 같은 이유로 `ATE`/`CATE`/`HTE`/`DML`/`SCM`/`SMOTE`/`ARIMA` 등 acronym은
  대문자로만 매칭. 소문자 키워드는 대소문자 무시.
- **bare 키워드 3개 제거** (Phase 0 실측 근거):
  - `causal` 단독 삭제 → causal attention/mask/LM/decoder(LLM 논문) 대량 오탐 제거. 구체 용어만 유지.
  - `temporal` 단독 삭제 → temporal graph/video 논문 오탐 제거. `time series` 등 구체 용어로 대체.
  - `calibration` 단독 삭제 → LLM uncertainty calibration 오탐 제거. `probability calibration` 등으로 한정.

**실측 물량 (3일창, dedup 후):** 레인 4 = **47.7건/일** (HF Daily 16.7 + arXiv raw niche 31).
niche 억제 전 원시 arXiv는 약 200건/일 → 키워드 필터로 억제. 이 물량은 Haiku 필터(§4.1) 입력으로도,
T2 인과 쿼터(§2.1)에도 충분하며 과하지 않다.

### 3.6 레인 5 — 실무 블로그 (RSS)

```yaml
practitioner:
  - Towards Data Science
  - KDnuggets
  - Machine Learning Mastery
  - Sebastian Raschka (Ahead of AI)
  - Eugene Yan
  - Chip Huyen
  - Lilian Weng
  - Analytics Vidhya
```

### 3.7 레인 6 — AI 미디어 (RSS + 웹서치)

T1 카테고리(Agent / LLM·FM / MLOps / 산업적용사례)의 **주 공급원.**
v2에서 누락되어 매일 8건이 채워지지 않는 버그가 있었다.

```yaml
media:
  - MIT Technology Review
  - IEEE Spectrum
  - TechCrunch (AI 섹션)
  - VentureBeat (AI 섹션)
  - Ars Technica
  - Wired (AI)
  # Semafor Tech — 제외 확정 (Phase 0): 테크 전용 피드 없음. 전 사이트 rss.xml만 살아있어
  #   레인 6을 비테크 일반뉴스로 오염(62→162건). 테크 전용 피드 확보 시 복원.

research_house:      # 자체 조사 → source_tier 1
  - Deloitte Insights
  - Gartner
  - IDC
  - McKinsey / BCG / Accenture (AI 관련)

corporate_newsroom:  # 자체 발표 → source_tier 1
  - 기업 공식 뉴스룸 (accenture, ey, ibm 등)
```

RSS 미제공 매체는 카테고리별 키워드 웹서치로 보완.

### 3.8 레인 7 — GitHub Releases (보조)

```yaml
repos:
  - microsoft/LightGBM
  - dmlc/xgboost
  - py-why/dowhy
  - py-why/EconML
  - uber/causalml
  - shap/shap
  - Nixtla/statsforecast
  - yzhao062/pyod
  - mlflow/mlflow
  - langchain-ai/langgraph
```

**필터**: 메이저/마이너 릴리스만 (패치 x.y.Z 제외). Pre-release 제외.
물량이 적으므로 **없는 날이 정상.**

### 3.9 국문 소스 (보조)

**보조 레인.** 매일 찾지 않고 RSS로 나오면 줍는다.
- 대상: 네이버 D2, 카카오, 토스, 당근, 우아한형제들, LG AI연구원, SKT, 삼성SDS
- 제외: 국내 IT 언론(영어 원문 번역 전재가 많아 중복 유발)

### 3.9.1 레인 9 — 모델 릴리스 (HuggingFace Hub) *(Phase 4 작업 2)*

**왜.** 모델 릴리스(Kimi K3, TabFM, Chronos, TimesFM …)는 예외 없이 HF Hub 에 뜬다 →
"빅테크가 블로그를 썼는가"(레인 1)에 의존하지 않는 **결정적 경로**. 레인 7(GitHub 릴리스)과
합치지 않는다 — 레인 7 이 0.4 인 건 "대부분 버그픽스"라서고, 모델 공개는 성격이 달라
사용자 관심사(tabular/timeseries 파운데이션 모델)와 직결된다. **lane_weight 0.8, source_tier 1(원 소스).**

**firehose 방지 (필수).** HF 는 하루 수백 개(대부분 파인튜닝/양자화 파생)라 그대로 붙이면 arXiv
firehose 재현. 2단 필터(`config/sources.yaml` `lane9_hf`):
- (a) **org 화이트리스트** — 프론티어 랩 16곳(moonshotai, deepseek-ai, Qwen, google, meta-llama,
  microsoft, openai, mistralai, PriorLabs(TabPFN), nvidia, apple …).
- (b) **likes/downloads 임계치**(20 / 1000, OR) + **파생 이름 패턴 제외**(GGUF, AWQ, NVFP4, BF16,
  DFlash, block7 …). 3일 롤링 창(§3.10) 동일.

**목표 물량 0~5건/일.** 실측(2026-07-18, 창 06-27~07-14, 18일): 8건 ≈ **0.5/일** — 전부 정상
플래그십(google/tabfm, DeepSeek-V4, Leanstral, Nemotron-Audex, GELab-Zero). 초기 필터가 느슨해
nvidia 의 타 랩 모델 NVFP4 재포장·deepseek draft(block7)가 새어 이름 패턴을 보강함. 초과 시 재튜닝.

### 3.10 수집 창

**최근 3일 롤링** + `seen.json` 필터.
당일만 보면 주말·공휴일에 구멍이 나고, 3일 롤링해도 중복은 seen.json이 막는다.

### 3.11 중복 제거

`data/seen.json` — URL 정규화 후 해시 인덱스.

```json
{
  "url_hash": {
    "url": "...",
    "title": "...",
    "category": "causal-inference",
    "source_tier": 2,
    "first_seen": "2026-07-16",
    "tags": ["#double-ml"]
  }
}
```

- 수집 직후 필터링에 사용
- **"↳ 연결된 이전 기사" 기능의 소스**로 겸용
- 보존 기간: 180일

---

## 4. 선별·랭킹

### 4.1 2단 모델 배분 (비용 통제)

| 단계 | 모델 | 입력 | 출력 |
|---|---|---|---|
| 필터·랭킹 | **Haiku** | 수집물 50~100건 | 카테고리 배정 + 점수 |
| 집필·해석 | **Sonnet** | 선별된 12~16건 | 요약 + 2슬롯 |

### 4.2 랭킹 스코어

```
final_score = base_score × lane_weight × tier_multiplier
```

- `base_score` — Haiku가 0~10으로 판정. 기준:
  1. **신규성** — 기존 방식 대비 새로운가
  2. **재현가능성** — 코드/모델 공개 여부
  3. **정형데이터 적용 가능성** ← 사용자 필터의 핵심 축
  4. 구체성 — 수치·실험·사례가 있는가 (마케팅 문구 배제)
- `lane_weight` — §3.1 (0.4 ~ 1.0)
- `tier_multiplier` — §3.1.1 (Tier 5 = 0.5 페널티)

카테고리별 쿼터(§2.1) 내에서 `final_score` 상위부터 채운다.
쿼터 하한(T2/T3)을 채울 후보가 없으면 **그냥 비운다.**

### 4.3 학습 루프

`data/preferences.md` — 👍/👎 피드백 누적. 랭킹 프롬프트에 주입.
승인 대기(HITL) 없음 — 데일리 cron과 상충하므로 **사후 피드백** 방식.

---

## 5. 발행

### 5.1 사이트 구조

```
/index.html                        오늘자 (카테고리별 오늘 뉴스만)
/news/YYYY/MM/DD.html              일별
/category/ai-agent.html            카테고리 누적 × 8
/category/llm-foundation-model.html
/category/deep-learning.html
/category/predictive-modeling.html
/category/causal-inference.html
/category/mlops.html
/category/practice.html
/category/industry-application.html
/archive.html                      전체 아카이브 (연>월>일 계층)
/weekly/YYYY-Www.html              주간 롤업 (금요일)
/feed.xml                          RSS
/data/published/YYYY-MM-DD.json    발행 원본 (SPEC §8 전문 + schema_version) ← 아래 생성 소스
/data/seen.json
/data/preferences.md
```

- **생성 소스 = `data/published/*.json`.** `src/build_site.py`가 이 JSON들만 읽어 index/일별/archive/
  category 를 **재렌더(LLM 0, $0)**. **재집필·재랭킹 금지** — 발행된 텍스트를 그대로 재사용한다.
- **링크는 상대경로.** GitHub 프로젝트 Pages 는 `/<repo>/` 하위라 절대경로 `/category/`가 깨진다.
  일별(깊이 3)=`../../../`, 카테고리(깊이 1)=`../`, 루트(index/archive)=``.
- **index = 최신 일별을 루트 경로로 재렌더**(복사 아님 — 깊이가 달라 상대경로가 다름).

### 5.2 index.html

- 그날치 카테고리별 뉴스만 표시
- 각 카테고리 헤더에 `전체 보기 ▸` → `/category/*.html`
- 상단 `TODAY'S TOP 3`

### 5.3 카테고리 누적 페이지

- **전 기간 누적, 최신순 리스트** (전문 미표시)
- 항목: `날짜 · [배지] 제목 · 1줄 요약 · 원문링크 · 일별 페이지 앵커`
- **태그 필터** (클라이언트 사이드 JS, 서버 불필요)
  - 예측 모델링 → `#tabular` `#XAI` `#timeseries` ...
  - 인과추론 → `#did` `#uplift` `#double-ml` ...
- 전문은 일별 페이지에만 존재 (누적 페이지 비대화 방지)

### 5.4 호스팅

단일 **public** 레포 (GitHub Pages 무료 조건)

---

## 6. 발송

### 6.1 채널 (독립 설계 — 하나가 죽어도 나머지 동작)

| 채널 | Phase | 역할 |
|---|---|---|
| **텔레그램** | 3 | 파이프라인 검증 + 폴백 |
| **카카오톡** | 3.5 | 주 채널 |
| GitHub Pages | 3 | 최종 보루 |

### 6.2 카카오톡

- API: `POST https://kapi.kakao.com/v2/api/talk/memo/default/send`
- 템플릿: **`object_type: "list"`**
  - `header_title`: `AI & ML Daily · 07/16`
  - `contents`: TOP 3 (각 title + link)
  - 버튼 → 전체 HTML
- 나에게 보내기 = 앱 검수·친구 동의 불필요, 무료
- **토큰**: access 6h / refresh 60일
  - 매 실행 refresh → access 재발급
  - refresh_token 재발급 시 → **GitHub Secrets를 REST API로 덮어쓰기** (libsodium sealed box, PAT 필요)
  - 재발급은 유효기간 1개월 미만 남을 때만 → 실제 쓰기는 월 1회 수준

### 6.3 텔레그램

- BotFather `/newbot` → 토큰 (무기한)
- 본문: TOP 3 제목 + 각 1줄 + 전체 HTML 링크
- 4096자 제한 (여유 있음)

### 6.4 실패 정책

카카오 실패 → 텔레그램 폴백 + 로그.
카카오 API는 예고 없이 스펙이 깨진 전례가 있으므로 폴백을 상시 유지.

---

## 7. 실행

### 7.1 환경

- **GitHub Actions** (헤드리스, 서버 불필요, 월 2000분 무료)
- Cowork 예약작업 탈락 사유: PC 상시 기동 필요 + 날짜별 아카이브/중복제거 불가

### 7.2 스케줄

```yaml
on:
  schedule:
    - cron: '30 21 * * *'    # UTC 21:30 = KST 익일 06:30, 매일(주말 포함)
  workflow_dispatch:           # 수동 실행 지원
```

- KST 07:00 도착 목표. GH Actions는 부하 시 5~15분 지연이 흔하므로 30분 여유.
- **매일 발송(주말 포함).** 사용자 요청(2026-07-18)으로 평일 한정에서 전환. 근거·트레이드오프는 DECISIONS 참조.
- 월 실행 ~30회(구 평일 22회). §7.3 비용의 "22회" 월 환산은 30회 기준으로 비례 재계산할 것.

**타임존 (필수).** **Actions 러너는 UTC다. 모든 날짜는 KST(Asia/Seoul)로 계산한다.**
naive `date.today()`/`datetime.now()`를 쓰면 KST 06:30 실행이 UTC 전날로 찍혀 파일이 하루 밀린다
(실측 버그: 2026-07-17 06:30 실행이 `/news/2026/07/16.html`에 덮어씀). 조치:
- 코드: `src/config.py`의 `now_kst()`/`today_kst_iso()`(ZoneInfo("Asia/Seoul"))로 날짜·파일명·마스트헤드·
  first_seen·발송본문·수집창을 전부 계산. (외부 피드/기사 published_at 파싱만 원 소스 tz 유지)
- 워크플로: 잡에 `env: TZ: Asia/Seoul` (이중 안전장치). 커밋 메시지 날짜도 KST.
- 의존성: `tzdata`(Windows 로컬 등 시스템 tz DB 없는 환경 대비).

### 7.3 비용

- **Haiku 랭킹 실측 (Phase 1, 2026-07-16):** 1회 $0.0725 (297건 랭킹, 20호출,
  입력 26,582 / 출력 9,185 토큰). 평일 22회 월 환산 **$0.5~1.6**.
  - 상한 $1.6 = 첫 실행(seen.json 빈 상태, 297건 전량) × 22 기준.
  - 하한 $0.5 ≈ 정상 운영 시 일일 신규분(~99건, seen.json 필터 후) × 22 기준. 건당 $0.00024.
  - **v4 추정 $10~15는 과대. Haiku 실측 기준 $0.5~1.6로 갱신.**
- **Sonnet 집필 비용은 Phase 2에서 미측정.** 선별 12~16건에 요약+2슬롯 집필이 추가되면
  이 값이 크게 오른다 → **Phase 2에서 재측정 후 확정.**

**폭주 방지 (필수 구현)**
```yaml
max_tokens_per_call: 2000
daily_call_limit: 150
retry_limit: 3
daily_budget_usd: 1.0        # 초과 시 중단 + 텔레그램 알림
timeout_per_lane_sec: 120
```

### 7.4 Secrets

```
ANTHROPIC_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
KAKAO_REST_API_KEY
KAKAO_REFRESH_TOKEN
GH_PAT                  # Secrets 자기 갱신용
```

---

## 8. 데이터 스키마

```python
Item = {
  "url": str,
  "url_hash": str,
  "title": str,                    # 원문 제목
  "title_ko": str | None,          # 한글 재작성 제목/요약. Sonnet. content_type별 렌더 분기 (§2.4)
  "source_domain": str,
  "lane": int,                     # 1~7, §3.1
  "lane_weight": float,            # 0.4~1.0, §3.1
  "source_tier": int,              # 1~5, 원본성. §3.1.1
  "tier_multiplier": float,        # 1.0~0.5
  "venue": str | None,             # "NeurIPS 2026" 등, 레인2일 때
  "content_type": Literal["news", "paper", "release", "blog"],
  "category": str,                 # 8개 중 1
  "tags": list[str],
  "published_at": str,
  "collected_at": str,
  "abstract": str | None,          # 원문 초록/요약, 수집 시점 저장. Sonnet 집필 근거
  "base_score": float,             # Haiku 판정 0~10
  "final_score": float,            # base × lane_weight × tier_multiplier
  "summary": str,                  # Sonnet, 3~5문장
  "why_it_matters": str,           # 1~2문장
  "whats_different": str | None,   # 1~2문장, 비교 대상 없으면 None
  "related_prev": str | None,
  "is_top3": bool
}
```

---

## 9. Phase

| Phase | 산출물 | 완료 기준 |
|---|---|---|
| **0** | 수집기 **7레인**, 로컬 실행 | JSON 80~150건 나옴. **레인별 실제 물량 실측 + lane_weight 튜닝** |
| **1** | seen.json + Haiku 랭킹 | 같은 기사 이틀 연속 안 나옴 |
| **2** | Sonnet 집필 + HTML 템플릿 | **샘플 1회분 육안 확인 → 정지하고 목차·슬롯 재검토. 비용 실측** |
| **3** | GH Pages + Actions cron + 텔레그램 | 실제로 07:00에 도착 |
| **3.5** | 카카오톡 추가 | 카톡 도착, 실패 시 텔레그램 폴백 |
| **4** | **커버리지 개선**(수집 리콜·스코어 축 분리·이벤트 중요도 축) + 카테고리/아카이브 | **회귀 하네스(§12) 통과** — kimi-k3·icml-2026-awards 등 케이스가 해당일 브리핑에 실림 |

> **Phase 0과 Phase 2에서 반드시 멈춘다.**
> - Phase 0: 레인별 물량이 티어 설계와 맞는지 확인 (특히 인과추론 T2 승격이 타당한지)
> - Phase 2: "이건 아닌데"가 반드시 나온다. 여기서 고치는 게 이후보다 10배 싸다.

---

## 10. 미결정 사항

- [ ] 웹서치 API 선택 (Tavily / Brave / Anthropic web_search) → 레인 6 research_house·newsroom 복원 시
- [ ] "연결된 이전 기사" 매칭 방식 (임베딩 vs 키워드) → Phase 4
- [ ] HTML 디자인 세부 → Phase 2 샘플 후
- [ ] The Batch / Semafor 대체 소스 확보 (Phase 0에서 작동 피드 없음 확인)

**Phase 0에서 확정(미결정 해소):**
- ✅ 빅테크 블로그 RSS 피드 확정 (§3.2). Anthropic은 HTML 스크래퍼로 복원.
- ✅ 인과추론 T2 유지 확정 (§2.1).

**Phase 1에서 확정(미결정 해소, 2026-07-16):**
- ✅ `lane_weight` **전부 동결** (변경 없음). 진입률 분포가 설계 의도와 일치. DECISIONS.md 참조.
- ✅ Tier 5 **자동 판정 안 함**. 도메인 화이트리스트 유지. DECISIONS.md 참조.

---

## 11. 원칙

1. **SPEC 없으면 코드 없다. PLAN 없으면 구현 없다.**
2. 요구사항 변경 시 SPEC → PLAN → TASK 역추적 갱신.
3. 빈 섹션은 결함이 아니다. 억지로 채우면 뉴스레터가 죽는다.
4. 채널은 서로 독립. 하나가 실패해도 나머지는 동작.
5. 논문·릴리스는 API로. 검색에 맡기지 않는다.
6. **해석 슬롯에 억지를 넣지 않는다.** 비교 대상이 없으면 생략한다.
7. **소스 판정은 "벤더냐"가 아니라 "원 소스냐"로 한다.** 벤더 배제는 잘못된 축이다.
8. **관심도(lane_weight)와 원본성(source_tier)은 독립 축이다.** 하나로 합치지 않는다.

---

## 12. 회귀 하네스 (Phase 4 커버리지 게이트)

**문제.** 이전 시스템에는 "누가 말했나"(lane_weight × tier) 축만 있고 **"이게 오늘 이 분야의
메인 사건인가"** 축이 없었다. 그래서 카테고리 무관하게 같은 실패(대형 사건 미포착)가 반복됐다
(실례: 2026-07-16 Kimi K3 공개 · ICML 2026 어워드 미포착). 이건 특정 소스 누락이 아니라 축의 부재다.

**하네스.** 이 실패를 고정 케이스로 박아 Phase 4의 완료 게이트로 삼는다.

- `tests/coverage_cases.yaml` — 놓쳤던(놓쳐선 안 될) 사건을 **카테고리별로 분산**해 케이스화.
  각 케이스: `id / date / must_contain_any / expect_category / expect_in_output`.
- `scripts/replay.py` — 특정 날짜로 `collect → dedup → (rank → select)` 재실행 후,
  케이스별 PASS/FAIL 과 **탈락 단계**(collect / dedup / rank / select)를 출력. 기본은 무비용
  (collect+dedup); `--rank` 로 랭킹·선별까지. 케이스 사건일이 수집 창(§3.10, 3일) 밖이면 SKIP.
- **단계별 스냅샷** `data/raw/{stage}/YYYY-MM-DD.json` — 파이프라인이 collect/dedup/rank/select
  각 단계를 날짜별로 남긴다(best-effort). 이전엔 최종 채택분만 남아 사후 진단이 불가능했다.

**완료 기준.** kimi-k3·icml-2026-awards 등 케이스가 해당일 브리핑에 실려 FAIL 0.
작업 3(리콜)·5(가산 전환)·6(중요도 축) 은 하나의 조치이며, 이 게이트로 검증한다.