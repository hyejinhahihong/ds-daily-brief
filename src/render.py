"""HTML rendering — daily accordion page (SPEC §5 / docs/DESIGN.md v3).

v3 (2026-07-16, 2차 육안 검토 반영):
  - 제목 언어 content_type 분기 (title_ko): paper=원문 주/한글 부, 그 외=한글 주/원문 부 (§2).
  - 본문 bold 강조 (형광펜 금지): write.py 가 `**...**` 마커 → escape 후 <strong> 치환 (§3).
  - 마스트헤드(뉴스레터 제호): 아이브로우 + 제호 + 날짜·건수 + 2px 구분선 (§4).
  - TODAY'S TOP 3 에 [카테고리] 표시 (§4-1).
  - TOC: title_ko 우선 + 2줄 허용(clamp:2, "…" 잘림 해결) + 폭 260 (§5).
  - "다루는 주제" 하단 푸터: 8개 카테고리 + 설명 + /category/*.html 링크(미생성, 링크만) (§6).
  - 데스크톱 중앙 정렬 + 3단 브레이크포인트(<900 / 900~1199 상단목차 폴백 / ≥1200 사이드 TOC) (§5).
v2 유지: Claude warm-neutral 팔레트 + 단일 teal 액센트, 회색 배지, 아코디언, 카테고리 색 없음.
Self-contained (one CDN link for Pretendard). Daily page only.
"""

from __future__ import annotations

import datetime
import html
import re

from .models import Item
from .write import is_grounding_weak

# content_type → (배지 이모지, 라벨). 색 구분 없음 — 회색 배지 1종 (DESIGN §3).
_BADGE = {"news": ("📰", "뉴스"), "paper": ("📄", "논문"),
          "release": ("📦", "릴리스"), "blog": ("✍️", "블로그")}

# 카테고리 설명 1줄 (SPEC §2.1 기준, DESIGN §6). 섹션 헤더와 "다루는 주제" 푸터가 공유.
_CAT_DESC = {
    "ai-agent": "AI 에이전트 — 자율 실행·툴 사용·멀티에이전트 협업",
    "llm-foundation-model": "LLM·파운데이션 모델 — 사전학습·정렬·추론",
    "deep-learning": "딥러닝 — 아키텍처·학습기법 자체",
    "predictive-modeling": "예측 모델링 — 정형데이터, tabular·이상탐지·시계열·XAI",
    "causal-inference": "인과추론 — 인과추론 기법, causal ML, 인과관계 기반 의사결정",
    "mlops": "MLOps — ML 운영·엔지니어링, 평가·서빙·파이프라인",
    "practice": "실무자의 작업 방식·회고·팁 — FDE 사례, 현장 구축, 시행착오",
    "industry-application": "산업 적용 사례 — 산업 현장의 AI/ML 적용",
}

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

_CSS = """
:root{
  --accent:#5DB8A6; --accent-hover:#479B8B; --accent-weak:#E8F4F1;
  --focus-ring:rgba(93,184,166,.5);
  --bg:#FAF9F5; --bg-subtle:#F0EEE6; --border:#E7E3D9;
  --text:#1F1E1D; --text-2:#6B6862; --text-3:#A39E94;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --accent:#6FC7B5; --accent-hover:#82D4C3; --accent-weak:rgba(93,184,166,.14);
  --focus-ring:rgba(111,199,181,.55);
  --bg:#1F1E1D; --bg-subtle:#292826; --border:#3A3833;
  --text:#F0EEE6; --text-2:#A8A39A; --text-3:#6E6A62;
}}
:root[data-theme="dark"]{
  --accent:#6FC7B5; --accent-hover:#82D4C3; --accent-weak:rgba(93,184,166,.14);
  --focus-ring:rgba(111,199,181,.55);
  --bg:#1F1E1D; --bg-subtle:#292826; --border:#3A3833;
  --text:#F0EEE6; --text-2:#A8A39A; --text-3:#6E6A62;
}
*{box-sizing:border-box}
html,body{overflow-x:hidden}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{color:var(--accent-hover);text-decoration:underline}
strong{font-weight:600;color:var(--text)}
:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}

/* 모바일 우선 단일 컬럼 (<1200px). 덩어리 중앙 정렬은 margin:0 auto. */
.page{max-width:760px;margin:0 auto;padding:20px 18px 40px}

/* --- 마스트헤드 (뉴스레터 제호) --- */
.mast{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
  padding-bottom:14px;border-bottom:2px solid var(--text);margin-bottom:24px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.12em;color:var(--accent);
  text-transform:uppercase;margin:0 0 6px}
.mast-title{font-size:26px;font-weight:600;margin:0;letter-spacing:-.01em;line-height:1.15}
.mast-date{font-size:14px;color:var(--text-2);margin-top:8px}
.themebtn{flex:none;background:var(--bg-subtle);border:1px solid var(--border);color:var(--text-2);
  border-radius:20px;padding:5px 12px;font-size:13px;cursor:pointer;font-family:inherit}
.topnav{margin-top:11px;display:flex;gap:16px;font-size:13px}
.topnav a{color:var(--text-2);font-weight:500} .topnav a:hover{color:var(--accent)}
@media (min-width:640px){.mast-title{font-size:31px}}

/* --- TODAY'S TOP 3 --- */
.top3{background:var(--accent-weak);border-radius:12px;padding:14px 18px;margin-bottom:24px}
.top3 h2{font-size:13px;font-weight:600;letter-spacing:.06em;color:var(--accent);margin:0 0 8px}
.top3 ol{margin:0;padding:0;list-style:none}
.top3 li{padding:4px 0 4px 22px;position:relative;font-size:15px;color:var(--text)}
.top3 li::before{content:"\\2605";position:absolute;left:0;color:var(--accent);font-size:12px;top:7px}
.top3 .t3cat{color:var(--text-2);font-size:12px;margin-right:5px}
.top3 a{color:var(--text)} .top3 a:hover{color:var(--accent-hover)}

/* --- 목차 (TOC) --- */
.toc{margin-bottom:26px}
.toc h2{font-size:12px;font-weight:600;letter-spacing:.06em;color:var(--text-2);margin:0 0 8px}
.toc ul{margin:0;padding:0;list-style:none}
.toc li{padding:6px 0;border-top:1px solid var(--border)}
.toc li:first-child{border-top:none}
.toc .r{display:flex;gap:6px;align-items:baseline;font-size:14px}
.toc .nm{font-weight:500;color:var(--text)} .toc a:hover .nm{color:var(--accent)}
.toc .cnt{color:var(--text-3);font-size:12px}
.toc .lead{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  font-size:12px;color:var(--text-2);margin-top:2px;line-height:1.4}
.toc li.active .nm{color:var(--accent)}
.toc li.active{border-left:2px solid var(--accent);padding-left:8px;margin-left:-10px}

/* --- 섹션 --- */
.sec{margin:0 0 34px;scroll-margin-top:14px}
.sec-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin:0 0 2px;padding-top:6px}
.sec-h .nm{font-size:20px;font-weight:600}
.sec-h .cnt{font-size:13px;color:var(--text-3)}
.sec-h .all{font-size:12px;color:var(--text-3);margin-left:auto}
.sec-h .all span{color:var(--text-2)}
.sec-h .exp{font-size:12px;background:none;border:1px solid var(--border);color:var(--text-2);
  border-radius:14px;padding:2px 10px;cursor:pointer;font-family:inherit}
.sec-desc{font-size:13px;color:var(--text-2);margin:0 0 8px}
.sec-empty{font-size:14px;color:var(--text-3);padding:4px 0 6px}
.backtop{display:inline-block;font-size:12px;color:var(--text-3);margin-top:6px}

/* --- 아이템 (아코디언) — 거터(번호) + 단일 콘텐츠 컬럼 (DESIGN §3 v4). 좌측 정렬선 1개. --- */
.item{border-bottom:1px solid var(--border);--gutter:28px}
.item>summary{list-style:none;cursor:pointer;padding:16px 26px 16px 0;position:relative;
  display:grid;grid-template-columns:var(--gutter) 1fr;align-items:start}
.item>summary::-webkit-details-marker{display:none}
.item>summary::after{content:"\\25B8";position:absolute;right:2px;top:16px;color:var(--text-3);
  font-size:13px;transition:transform .15s;display:inline-block}
.item[open]>summary::after{transform:rotate(90deg)}
.num{font-size:13px;color:var(--text-3);font-variant-numeric:tabular-nums;font-weight:500;padding-top:3px}
.t3star{color:var(--accent);font-size:11px;margin-right:2px}
.body-col{min-width:0}
.it-title{display:block;font-size:18px;font-weight:600;color:var(--text);line-height:1.4}
.item>summary:hover .it-title{color:var(--accent)}
.it-sub{display:block;font-size:13px;color:var(--text-2);margin-top:3px;line-height:1.35}
.it-meta{display:block;font-size:13px;color:var(--text-2);margin-top:6px}
.it-lede{display:block;font-size:15px;color:var(--text-2);margin-top:7px;line-height:1.5}
.item[open] .it-lede{color:var(--text)}
/* 접힘 본문도 콘텐츠 컬럼에 정렬 (거터만큼 들여씀) */
.it-body{padding:0 0 20px var(--gutter)}
.it-body p{margin:0 0 10px}
@media (min-width:900px){.item{--gutter:40px}}
.slot-l{font-size:12px;font-weight:500;letter-spacing:.04em;color:var(--text-2);margin:14px 0 2px}
.tags{margin-top:10px}
.tag{display:inline-block;font-size:12px;color:var(--text-2);background:var(--bg-subtle);
  border:1px solid var(--border);border-radius:12px;padding:1px 9px;margin:0 5px 5px 0}
.prev{font-size:13px;color:var(--text-3);margin-top:8px}
.src-cta{display:inline-block;margin-top:12px;font-size:14px;font-weight:500;color:var(--accent)}
.weak{color:var(--accent);font-size:12px;border:1px solid var(--accent);border-radius:5px;
  padding:0 6px;margin-left:6px}

/* --- "다루는 주제" 푸터 --- */
.topics{margin-top:36px;padding-top:22px;border-top:2px solid var(--text)}
.topics h2{font-size:15px;font-weight:600;margin:0 0 12px}
.topics ul{margin:0;padding:0;list-style:none}
.topics li{padding:7px 0;border-top:1px solid var(--border);font-size:13px;color:var(--text-2)}
.topics li:first-child{border-top:none}
.topics .tnm{font-weight:600;color:var(--accent);margin-right:6px}

/* --- 데스크톱 (≥1200px): 좌측 sticky TOC(260) + 본문(720), 덩어리 중앙 정렬 --- */
@media (min-width:1200px){
  /* max-width = 260+44+720 그리드(1024) + 좌우 padding(18*2). box-sizing:border-box
     라 padding 을 포함해야 본문 720 이 찌그러지지 않는다. */
  .page{max-width:1060px;display:grid;grid-template-columns:260px minmax(0,720px);
    column-gap:44px;justify-content:center;align-items:start;padding-top:28px}
  .mast{grid-column:1/3}
  .toc{grid-column:1;grid-row:2/999;position:sticky;top:24px;margin:0;align-self:start}
  .top3,.main{grid-column:2}
  .topics{grid-column:1/3}
}
"""

# archive/category(리스트 페이지) 전용 CSS. _CSS 뒤에 이어붙여 팔레트·타이포 공유.
_CSS_LIST = """
.crumb{font-size:13px;color:var(--text-2);margin:0 0 14px}
.crumb a{color:var(--text-2)} .crumb a:hover{color:var(--accent)}
.otherk{font-size:13px;color:var(--text-2);margin:0 0 20px;line-height:1.9}
.otherk a{display:inline-block;margin-right:4px;padding:2px 9px;border:1px solid var(--border);
  border-radius:13px;color:var(--text-2)}
.otherk a:hover{color:var(--accent);text-decoration:none;border-color:var(--accent)}
.catdesc{font-size:14px;color:var(--text-2);margin:0 0 18px}
/* 태그 필터 */
.tfilter{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 20px}
.tfilter button{font-size:12px;font-family:inherit;cursor:pointer;padding:3px 11px;border-radius:14px;
  border:1px solid var(--border);background:var(--bg-subtle);color:var(--text-2)}
.tfilter button.on{background:var(--accent-weak);border-color:var(--accent);color:var(--accent)}
/* 리스트 행 */
.clist{list-style:none;margin:0;padding:0}
.crow{padding:13px 0;border-top:1px solid var(--border)}
.crow:first-child{border-top:none}
.crow .cdate{font-size:12px;color:var(--text-3);font-variant-numeric:tabular-nums;margin-right:7px}
.crow .cbadge{font-size:12px;color:var(--text-2);margin-right:6px}
.crow .ctitle{font-size:16px;font-weight:600;color:var(--text);line-height:1.4}
.crow .clede{display:block;font-size:14px;color:var(--text-2);margin-top:4px;line-height:1.5}
.crow .clinks{margin-top:5px;font-size:13px}
.crow .clinks a{margin-right:12px}
.crow .ctag{font-size:11px;color:var(--text-3);margin-left:6px}
.empty{color:var(--text-3);font-size:14px;padding:10px 0}
/* 아카이브 계층 */
.arcyear{font-size:22px;font-weight:600;margin:26px 0 4px}
.arcmonth{font-size:15px;font-weight:600;color:var(--text-2);margin:16px 0 6px}
.arclist{list-style:none;margin:0;padding:0}
.arcrow{padding:9px 0;border-top:1px solid var(--border);display:flex;gap:10px;align-items:baseline}
.arcrow:first-child{border-top:none}
.arcrow .ad{font-weight:500} .arcrow .ac{font-size:13px;color:var(--text-3);margin-left:auto}
"""

_JS = """
(function(){
var r=document.documentElement,k="dsb-theme",s=localStorage.getItem(k);
if(s)r.dataset.theme=s;
document.getElementById('tbtn').addEventListener('click',function(){
  var cur=r.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  var n=cur==='dark'?'light':'dark';r.dataset.theme=n;localStorage.setItem(k,n);});
// 섹션 전체 펼치기/접기
document.querySelectorAll('.exp').forEach(function(b){b.addEventListener('click',function(){
  var sec=document.getElementById(b.dataset.sec);
  var ds=sec.querySelectorAll('details.item'),open=b.dataset.state!=='open';
  ds.forEach(function(d){d.open=open;});
  b.dataset.state=open?'open':'closed';b.textContent=open?'전체 접기':'전체 펼치기';});});
// 스크롤 위치 카테고리 TOC 활성 (데스크톱 사이드 TOC)
var links={};document.querySelectorAll('.toc li[data-cat]').forEach(function(li){links[li.dataset.cat]=li;});
var obs=new IntersectionObserver(function(es){es.forEach(function(e){
  if(e.isIntersecting){Object.values(links).forEach(function(l){l.classList.remove('active');});
    if(links[e.target.id])links[e.target.id].classList.add('active');}});},
  {rootMargin:'-10% 0px -80% 0px'});
document.querySelectorAll('section.sec').forEach(function(s){obs.observe(s);});
})();
"""

_EMPH_RE = re.compile(r"\*\*(.+?)\*\*", re.S)


def _esc(s: str) -> str:
    return html.escape(s or "")


def _emph(s: str) -> str:
    """Escape text, then convert our own `**...**` markers to <strong>.

    Escape-first makes this injection-safe: any HTML in the model output is
    neutralized, and only our sentinel survives to become markup. Leftover
    unbalanced markers (rare, e.g. a bold phrase split across sentences) are
    dropped so no stray `**` shows.
    """
    out = _EMPH_RE.sub(r"<strong>\1</strong>", _esc(s))
    return out.replace("**", "")


def _first_sentence(s: str) -> tuple[str, str]:
    """Split a Korean/EN summary into (first sentence, rest)."""
    s = (s or "").strip()
    m = re.search(r"(다\.|[.!?])(\s|$)", s)
    if not m:
        return s, ""
    i = m.end(1)
    return s[:i].strip(), s[i:].strip()


def _titles(it: Item) -> tuple[str, str | None]:
    """(primary, secondary) display titles by content_type (DESIGN §2).

    paper  → 원문 제목 주 / title_ko 부.
    else   → title_ko 주 / 원문 제목 부.
    """
    if it.content_type == "paper":
        primary, secondary = it.title, it.title_ko
    else:
        primary = it.title_ko or it.title
        secondary = it.title if it.title_ko else None
    if secondary and secondary.strip() == (primary or "").strip():
        secondary = None
    return primary or "", secondary


def _toc_title(it: Item) -> str:
    """TOC lead — 한글이 폭 대비 정보량이 높아 title_ko 우선 (DESIGN §5)."""
    return it.title_ko or it.title


def _item_html(it: Item, num: int) -> str:
    emoji, label = _BADGE.get(it.content_type, ("•", it.content_type))
    anchor = it.url_hash[:12]
    # 메타 라인: 배지(메타데이터) · 출처 · venue — 전부 --text-2 같은 급 (DESIGN §3 v4)
    meta = f"{emoji} {label} · {_esc(it.source_domain)}"
    if it.venue:
        meta += f" · {_esc(it.venue)}"
    if is_grounding_weak(it):
        meta += '<span class="weak">원문 근거 부족</span>'
    primary, secondary = _titles(it)
    lede, rest = _first_sentence(it.summary or "")
    opn = " open" if it.is_top3 else ""

    p = [f'<details class="item" id="{anchor}"{opn}><summary>']
    # is_top3 → ★ 마커(번호 옆, --accent, 툴팁). 상단 TOP 3 박스와 같은 글리프(U+2605).
    # "왜 이것만 펼쳐졌지"를 없앰: 펼침 규칙(TOP 3만 open)을 시각적으로 드러낸다.
    star = '<span class="t3star" title="오늘의 TOP 3">★</span>' if it.is_top3 else ''
    p.append(f'<span class="num">{star}{num:02d}</span>')
    p.append('<span class="body-col">')
    p.append(f'<span class="it-title">{_esc(primary)}</span>')
    if secondary:
        p.append(f'<span class="it-sub">{_esc(secondary)}</span>')
    p.append(f'<span class="it-meta">{meta}</span>')
    if lede:
        p.append(f'<span class="it-lede">{_emph(lede)}</span>')
    p.append('</span>')  # /body-col
    p.append('</summary><div class="it-body">')
    if rest:
        p.append(f"<p>{_emph(rest)}</p>")
    if it.why_it_matters:
        p.append(f'<div class="slot-l">WHY IT MATTERS</div><p>{_emph(it.why_it_matters)}</p>')
    if it.whats_different:  # None → 슬롯 생략 (SPEC 원칙 6)
        p.append(f'<div class="slot-l">WHAT\'S DIFFERENT</div><p>{_emph(it.whats_different)}</p>')
    if it.related_prev:
        p.append(f'<div class="prev">↳ 연결된 이전 기사: {_esc(it.related_prev)}</div>')
    if it.tags:
        chips = "".join(f'<span class="tag">#{_esc(t)}</span>' for t in it.tags)
        p.append(f'<div class="tags">{chips}</div>')
    p.append(f'<a class="src-cta" href="{_esc(it.url)}" target="_blank" rel="noopener">원문 보기 →</a>')
    p.append("</div></details>")
    return "".join(p)


def render_daily(items: list[Item], categories: list[dict], run_date: str,
                 prefix: str = "../../../") -> str:
    """일별 페이지. prefix = 사이트 루트까지의 상대경로.

    일별 파일은 news/YYYY/MM/DD.html(깊이 3)이라 기본 '../../../'.
    index.html(루트, 깊이 0)로 쓸 땐 prefix='' 로 호출. (GitHub 프로젝트 Pages 는
    /repo/ 하위라 절대경로 '/category/'가 깨진다 → 상대경로 필수.)
    """
    by_cat: dict[str, list[Item]] = {c["id"]: [] for c in categories}
    for it in items:
        if it.category in by_cat:
            by_cat[it.category].append(it)
    for lst in by_cat.values():
        lst.sort(key=lambda it: (it.final_score or 0), reverse=True)
    cat_name = {c["id"]: c["name"] for c in categories}

    # 마스트헤드 날짜: 2026 / 07 / 16 (목) · 16건
    d = datetime.date.fromisoformat(run_date)
    date_line = (f"{run_date[:4]} / {run_date[5:7]} / {run_date[8:10]} "
                 f"({_WEEKDAY_KO[d.weekday()]}) · {len(items)}건")

    # TOP 3 — [카테고리] + 주 제목
    top3 = sorted([it for it in items if it.is_top3],
                  key=lambda it: (it.final_score or 0), reverse=True)
    top3_html = ""
    if top3:
        lis = ""
        for it in top3:
            cat = _esc(cat_name.get(it.category, it.category or ""))
            lis += (f'<li><a href="#{it.url_hash[:12]}">'
                    f'<span class="t3cat">[{cat}]</span>{_esc(_titles(it)[0])}</a></li>')
        top3_html = f'<section class="top3"><h2>TODAY\'S TOP 3</h2><ol>{lis}</ol></section>'

    # TOC — 신규 있는 카테고리만 + 1위 제목(title_ko 우선, 2줄 허용)
    toc_lis = ""
    for c in categories:
        lst = by_cat[c["id"]]
        if not lst:
            continue
        lead = _esc(_toc_title(lst[0]))
        toc_lis += (
            f'<li data-cat="{c["id"]}"><a href="#{c["id"]}">'
            f'<span class="r"><span class="nm">{_esc(c["name"])}</span>'
            f'<span class="cnt">{len(lst)}</span></span>'
            f'<span class="lead">{lead}</span></a></li>'
        )
    toc_html = f'<nav class="toc" id="toc"><h2>오늘의 목차</h2><ul>{toc_lis}</ul></nav>'

    # 섹션
    secs = []
    for c in categories:
        cid = c["id"]
        lst = by_cat[cid]
        desc = _CAT_DESC.get(cid, "")
        if lst:
            head = (
                f'<div class="sec-h"><span class="nm">{_esc(c["name"])}</span>'
                f'<span class="cnt">{len(lst)}건</span>'
                f'<span class="all"><a href="{prefix}category/{cid}.html">주제별 전체 보기 ↗</a></span>'
                f'<button class="exp" type="button" data-sec="{cid}">전체 펼치기</button></div>'
            )
            body = "".join(_item_html(it, i + 1) for i, it in enumerate(lst))
            secs.append(
                f'<section class="sec" id="{cid}">{head}'
                f'<div class="sec-desc">{_esc(desc)}</div>{body}'
                f'<a class="backtop" href="#toc">↑ 목차로 돌아가기</a></section>'
            )
        else:
            secs.append(
                f'<section class="sec" id="{cid}">'
                f'<div class="sec-h"><span class="nm">{_esc(c["name"])}</span></div>'
                f'<div class="sec-desc">{_esc(desc)}</div>'
                f'<div class="sec-empty">금일 신규 없음</div></section>'
            )

    # "다루는 주제" 푸터 — category/*.html 링크(상대경로) + 섹션 헤더와 동일 설명 재사용
    topic_lis = "".join(
        f'<li><a class="tnm" href="{prefix}category/{c["id"]}.html">{_esc(c["name"])}</a>'
        f'{_esc(_CAT_DESC.get(c["id"], ""))}</li>'
        for c in categories
    )
    topics_html = (f'<footer class="topics" id="topics"><h2>다루는 주제</h2>'
                   f'<ul>{topic_lis}</ul></footer>')

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI &amp; ML News Letter · {run_date[5:].replace('-', '/')}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header class="mast">
    <div class="mast-l">
      <div class="eyebrow">DAILY BRIEFING</div>
      <h1 class="mast-title">AI &amp; ML News Letter</h1>
      <div class="mast-date">{date_line}</div>
      <nav class="topnav"><a href="{prefix}archive.html">📅 지난 브리핑</a>
        <a href="#topics">🗂 주제별 보기</a></nav>
    </div>
    <button id="tbtn" class="themebtn" type="button">🌓 테마</button>
  </header>
  {top3_html}
  {toc_html}
  <main class="main">{''.join(secs)}</main>
  {topics_html}
</div>
<script>{_JS}</script>
</body>
</html>
"""


# 리스트 페이지(archive/category)용 최소 테마 토글 JS.
_JS_THEME = """
(function(){var r=document.documentElement,k="dsb-theme",s=localStorage.getItem(k);
if(s)r.dataset.theme=s;var b=document.getElementById('tbtn');if(b)b.addEventListener('click',function(){
var cur=r.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
var n=cur==='dark'?'light':'dark';r.dataset.theme=n;localStorage.setItem(k,n);});})();
"""

# 카테고리 태그 필터 JS.
_JS_TAGFILTER = """
(function(){var btns=document.querySelectorAll('.tfilter button');if(!btns.length)return;
var rows=document.querySelectorAll('.crow');
btns.forEach(function(b){b.addEventListener('click',function(){
btns.forEach(function(x){x.classList.remove('on');});b.classList.add('on');
var t=b.dataset.tag;rows.forEach(function(r){
var tags=(r.dataset.tags||'').split(' ');
r.style.display=(!t||tags.indexOf(t)>=0)?'':'none';});});});})();
"""


def _page_head(title: str, extra_css: str = "") -> str:
    return (f'<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{_esc(title)}</title>\n'
            f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard'
            f'@v1.3.9/dist/web/static/pretendard.min.css">\n'
            f'<style>{_CSS}{extra_css}</style>\n</head>\n')


def _mast(eyebrow: str, title: str) -> str:
    return (f'<header class="mast"><div class="mast-l">'
            f'<div class="eyebrow">{eyebrow}</div>'
            f'<h1 class="mast-title">{_esc(title)}</h1></div>'
            f'<button id="tbtn" class="themebtn" type="button">🌓 테마</button></header>')


def render_archive(days: list[dict], prefix: str = "") -> str:
    """아카이브 — 연 > 월 > 일 계층, 최신순. 소스=published/*.json (재집필 없음).

    days: [{"run_date": "2026-07-17", "count": 14}, ...] (정렬 무관, 내부 정렬).
    """
    days = sorted(days, key=lambda d: d["run_date"], reverse=True)
    by_year: dict[str, dict[str, list[dict]]] = {}
    for d in days:
        y, m = d["run_date"][:4], d["run_date"][5:7]
        by_year.setdefault(y, {}).setdefault(m, []).append(d)

    blocks = []
    for y in sorted(by_year, reverse=True):
        blocks.append(f'<div class="arcyear">{y}</div>')
        for m in sorted(by_year[y], reverse=True):
            blocks.append(f'<div class="arcmonth">{int(m)}월</div><ul class="arclist">')
            for d in by_year[y][m]:
                rd = d["run_date"]
                wd = _WEEKDAY_KO[datetime.date.fromisoformat(rd).weekday()]
                href = f'{prefix}news/{rd[:4]}/{rd[5:7]}/{rd[8:10]}.html'
                blocks.append(
                    f'<li class="arcrow"><a class="ad" href="{href}">'
                    f'{rd[5:7]}/{rd[8:10]} ({wd})</a>'
                    f'<span class="ac">{d["count"]}건</span></li>'
                )
            blocks.append('</ul>')
    body = "".join(blocks) if days else '<div class="empty">아직 발행된 브리핑이 없습니다.</div>'

    return (_page_head("아카이브 · AI & ML News Letter", _CSS_LIST) +
            f'<body>\n<div class="page">\n'
            f'<div class="crumb"><a href="{prefix}index.html">홈</a> · 아카이브</div>\n'
            f'{_mast("ARCHIVE", "아카이브")}\n'
            f'<main class="main">{body}</main>\n'
            f'</div>\n<script>{_JS_THEME}</script>\n</body>\n</html>\n')


def render_category(cid: str, name: str, entries: list[tuple[str, Item]],
                    subtags: list[str], categories: list[dict], prefix: str = "../") -> str:
    """카테고리 누적 — 전 기간 리스트(최신순), 전문 미표시. 소스=published/*.json.

    entries: [(run_date, Item), ...]. 리스트 형식(레퍼런스 전문방식 거부, DECISIONS 참조).
    subtags: 이 카테고리의 태그 칩(없으면 필터 UI 생략).
    """
    entries = sorted(entries, key=lambda e: (e[0], e[1].final_score or 0), reverse=True)
    desc = _CAT_DESC.get(cid, "")

    # 다른 주제 링크 7개
    others = "".join(
        f'<a href="{prefix}category/{c["id"]}.html">{_esc(c["name"])}</a>'
        for c in categories if c["id"] != cid
    )
    other_html = f'<div class="otherk"><b>다른 주제:</b> {others}</div>'

    # 태그 필터 (subtags 있을 때만)
    filt = ""
    if subtags:
        chips = '<button class="on" data-tag="" type="button">전체</button>'
        chips += "".join(f'<button data-tag="{t}" type="button">#{t}</button>' for t in subtags)
        filt = f'<div class="tfilter">{chips}</div>'

    rows = []
    for rd, it in entries:
        emoji, label = _BADGE.get(it.content_type, ("•", it.content_type))
        primary = it.title_ko or it.title
        lede = _first_sentence(it.summary or "")[0]
        daily = f'{prefix}news/{rd[:4]}/{rd[5:7]}/{rd[8:10]}.html#{it.url_hash[:12]}'
        tagattr = " ".join(it.tags)
        tagchips = "".join(f'<span class="ctag">#{_esc(t)}</span>' for t in it.tags)
        rows.append(
            f'<li class="crow" data-tags="{_esc(tagattr)}">'
            f'<span class="cdate">{rd[5:7]}/{rd[8:10]}</span>'
            f'<span class="cbadge">{emoji} {label}</span>'
            f'<span class="ctitle">{_esc(primary)}</span>{tagchips}'
            f'<span class="clede">{_esc(lede)}</span>'
            f'<span class="clinks">'
            f'<a href="{_esc(it.url)}" target="_blank" rel="noopener">원문 →</a>'
            f'<a href="{daily}">그날 브리핑 ↗</a></span></li>'
        )
    body = (f'<ul class="clist">{"".join(rows)}</ul>' if rows
            else '<div class="empty">아직 이 주제의 누적 항목이 없습니다.</div>')

    return (_page_head(f"{name} · AI & ML News Letter", _CSS_LIST) +
            f'<body>\n<div class="page">\n'
            f'<div class="crumb"><a href="{prefix}index.html">홈</a> · '
            f'<a href="{prefix}archive.html">아카이브</a> · {_esc(name)}</div>\n'
            f'{_mast("CATEGORY", name)}\n'
            f'<div class="catdesc">{_esc(desc)}</div>\n'
            f'{other_html}\n{filt}\n'
            f'<main class="main">{body}</main>\n'
            f'</div>\n<script>{_JS_THEME}{_JS_TAGFILTER}</script>\n</body>\n</html>\n')
