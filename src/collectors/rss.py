"""
src/collectors/rss.py
RSS 뉴스 수집기 — M1 시장 테마 AI 브리핑용
Google News (business) + CNBC (world markets) + MarketWatch (top stories)

사용법:
    from src.collectors.rss import collect_news
    articles, lookback_hours = collect_news()
"""

import logging
import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# RSS 소스 정의
# ─────────────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "Google News (Business)",
        "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB",
        "tag": "google",
    },
    {
        "name": "CNBC (World Markets)",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
        "tag": "cnbc",
    },
    {
        "name": "MarketWatch (Top Stories)",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "tag": "marketwatch",
    },
]

# ─────────────────────────────────────────────
# Lookback 시간 결정
# ─────────────────────────────────────────────
KST = timezone(timedelta(hours=9))


def _get_lookback_hours() -> int:
    """
    월요일(KST) → 72시간 (금~일 커버)
    화~금 → 28시간 (어제 아침 이후)
    """
    now_kst = datetime.now(KST)
    weekday = now_kst.weekday()  # 0=월, 6=일
    if weekday == 0:  # 월요일
        return 72
    return 28


def _parse_pub_date(entry) -> datetime | None:
    """RSS entry에서 발행일을 UTC datetime으로 파싱."""
    raw = entry.get("published") or entry.get("updated") or ""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        st = entry.get("published_parsed") or entry.get("updated_parsed")
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _dedup_key(title: str) -> str:
    """제목 기반 중복 제거 키."""
    normalized = title.strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()


def _clean_html(text: str) -> str:
    """HTML 태그 + 엔티티 정리."""
    if not text:
        return ""
    # HTML 태그 제거
    text = re.sub(r"<[^>]+>", " ", text)
    # HTML 엔티티
    replacements = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&apos;": "'", "&#39;": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # 남은 &#xxx; 엔티티 제거
    text = re.sub(r"&#?\w+;", " ", text)
    # 연속 공백 정리
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ─────────────────────────────────────────────
# 메인 수집 함수
# ─────────────────────────────────────────────
def collect_news(max_per_feed: int = 15) -> tuple[list[dict], int]:
    """
    RSS 뉴스를 수집하고 lookback 시간 내 기사만 반환.

    Returns:
        (articles, lookback_hours)
        articles: [{"title": str, "summary": str, "source": str, "published": str}]
    """
    lookback_hours = _get_lookback_hours()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    all_articles = []
    seen_keys = set()

    for feed_info in RSS_FEEDS:
        name = feed_info["name"]
        url = feed_info["url"]
        tag = feed_info["tag"]

        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning("RSS 파싱 실패: %s — %s", name, feed.bozo_exception)
                continue

            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break

                title = _clean_html(entry.get("title") or "")
                if not title:
                    continue

                # 중복 제거
                key = _dedup_key(title)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # 날짜 필터
                pub_dt = _parse_pub_date(entry)
                if pub_dt and pub_dt < cutoff:
                    continue

                # 요약 추출 (전문 X — 토큰 절약)
                summary = _clean_html(entry.get("summary") or entry.get("description") or "")
                if len(summary) > 200:
                    summary = summary[:197] + "..."

                pub_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC") if pub_dt else "unknown"

                all_articles.append({
                    "title": title,
                    "summary": summary,
                    "source": tag,
                    "published": pub_str,
                })
                count += 1

            logger.info("RSS 수집: %s → %d건", name, count)

        except Exception as e:
            logger.warning("RSS 수집 실패: %s — %s", name, e)
            continue

    # 최신순 정렬
    all_articles.sort(key=lambda a: a["published"], reverse=True)

    logger.info("RSS 총 수집: %d건 (lookback: %dh)", len(all_articles), lookback_hours)
    return all_articles, lookback_hours


def format_news_context(articles: list[dict]) -> str:
    """수집된 기사를 LLM 컨텍스트 텍스트로 변환."""
    if not articles:
        return "(뉴스 수집 결과 없음)"

    lines = []
    for i, a in enumerate(articles, 1):
        line = f"{i}. [{a['source']}] {a['title']}"
        if a["summary"]:
            line += f"\n   → {a['summary']}"
        lines.append(line)

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 단독 테스트
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    articles, hours = collect_news()
    print(f"\n=== RSS 수집 결과 ({len(articles)}건, lookback {hours}h) ===\n")
    print(format_news_context(articles))
