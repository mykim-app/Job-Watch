"""API가 없는 채용게시판을 CSS selector 로 긁어오는 범용 수집기.

config.yaml 의 html_boards 항목에 selector 를 채워 넣으면 동작한다.
selector 가 비어 있거나 아무것도 못 찾으면 조용히 건너뛰고 로그만 남긴다.
"""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import Posting, parse_ymd, squeeze

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; job-watch/1.0; personal use)",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _text(node, selector: str) -> str:
    if not selector:
        return ""
    found = node.select_one(selector)
    return squeeze(found.get_text()) if found else ""


def _href(node, selector: str, base: str) -> str:
    target = node.select_one(selector) if selector else None
    if target is None and node.name == "a":
        target = node
    if target is None:
        target = node.select_one("a")
    if target is None:
        return ""
    href = target.get("href", "")
    if not href or href.startswith("javascript"):
        return ""
    return urljoin(base, href)


def fetch(board: dict, log) -> list[Posting]:
    name = board.get("name", board.get("key", "게시판"))
    sel = board.get("selectors", {}) or {}
    item_sel = squeeze(sel.get("item"))

    if not item_sel:
        log(f"{name}: 목록 selector 가 비어 있어 건너뜀 (README의 'HTML 게시판 추가' 참고)")
        return []

    try:
        r = requests.get(board["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as e:  # noqa: BLE001
        log(f"{name}: 페이지를 못 읽음 — {e}")
        return []

    base = board.get("link_base") or board["url"]
    nodes = soup.select(item_sel)
    if not nodes:
        log(f"{name}: '{item_sel}' 로 잡히는 항목이 0건. selector 를 다시 확인해야 함")
        return []

    out: list[Posting] = []
    for node in nodes:
        title = _text(node, sel.get("title", "")) or squeeze(node.get_text())[:120]
        if not title:
            continue
        out.append(
            Posting(
                source=board.get("key", "html"),
                source_label=name,
                org=_text(node, sel.get("org", "")) or name,
                title=title,
                url=_href(node, sel.get("link", ""), base),
                start_date=parse_ymd(_text(node, sel.get("date", ""))),
                end_date=parse_ymd(_text(node, sel.get("end_date", ""))),
            )
        )

    log(f"{name}: {len(out)}건 수집")
    return out
