"""신규 공고가 있을 때만 메일을 보낸다. 0건이면 아무것도 안 보낸다."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape


def _row(p: dict) -> str:
    d = p.get("d_day")
    dday = f"D-{d}" if isinstance(d, int) and d >= 0 else ("마감" if isinstance(d, int) else "")
    url = p.get("url") or ""
    title = escape(p.get("title", ""))
    title_html = f'<a href="{escape(url)}" style="color:#0B2A4A;">{title}</a>' if url else title
    meta = " · ".join(
        x for x in (p.get("source_label"), p.get("region"), p.get("hire_type"), dday) if x
    )
    return (
        '<tr><td style="padding:14px 0;border-bottom:1px solid #E3E6EC;">'
        f'<div style="font:600 13px/1.4 -apple-system,sans-serif;color:#5A6474;">{escape(p.get("org",""))}</div>'
        f'<div style="font:600 16px/1.5 -apple-system,sans-serif;margin:3px 0 5px;">{title_html}</div>'
        f'<div style="font:400 12px/1.4 -apple-system,sans-serif;color:#7A8598;">{escape(meta)}'
        f' · 접수 {escape(p.get("start_date","-"))} ~ {escape(p.get("end_date","-"))}</div>'
        "</td></tr>"
    )


def build_html(new_items: list[dict], today: str, site_url: str) -> str:
    rows = "".join(_row(p) for p in new_items)
    link = (
        f'<p style="font:400 13px/1.6 -apple-system,sans-serif;color:#5A6474;">'
        f'전체 목록: <a href="{escape(site_url)}" style="color:#0E7C6B;">{escape(site_url)}</a></p>'
        if site_url
        else ""
    )
    return f"""<!doctype html><html><body style="margin:0;background:#F7F8FA;padding:20px;">
<div style="max-width:640px;margin:0 auto;background:#fff;padding:24px;border:1px solid #E3E6EC;">
<div style="font:400 12px/1.4 ui-monospace,monospace;color:#7A8598;letter-spacing:.08em;">{escape(today)}</div>
<h1 style="font:700 22px/1.3 -apple-system,sans-serif;color:#0B2A4A;margin:6px 0 2px;">
전산·통신직 신규 공고 {len(new_items)}건</h1>
<p style="font:400 13px/1.5 -apple-system,sans-serif;color:#5A6474;margin:0 0 8px;">
어제 이후 새로 올라온 공고입니다. 이미 안내한 공고는 빠져 있습니다.</p>
<table style="width:100%;border-collapse:collapse;">{rows}</table>
{link}
</div></body></html>"""


def send(new_items: list[dict], today: str, site_url: str = "") -> bool:
    if not new_items:
        print("[mail] 신규 0건 — 발송 생략")
        return False

    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    to_addr = os.environ.get("MAIL_TO", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))

    if not all([host, user, password, to_addr]):
        print("[mail] SMTP 설정이 없어 발송 생략")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[전산·통신직] {today} 신규 공고 {len(new_items)}건"
    msg["From"] = os.environ.get("MAIL_FROM", user)
    msg["To"] = to_addr
    msg.set_content(
        "\n".join(
            f"- [{p.get('org','')}] {p.get('title','')} ({p.get('url','')})"
            for p in new_items
        )
    )
    msg.add_alternative(build_html(new_items, today, site_url), subtype="html")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
        print(f"[mail] {to_addr} 로 {len(new_items)}건 발송")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[mail] 발송 실패: {e}")
        return False
