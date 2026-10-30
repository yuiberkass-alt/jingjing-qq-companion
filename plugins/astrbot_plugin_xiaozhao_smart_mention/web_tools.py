"""Minimal, dependency-free web access for the group bot.

Two operations:
  * fetch_page(url)  - read an article the user pasted
  * search(query)    - Bing HTML results, no API key

Both refuse private/loopback targets and cap the amount of text they return.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
URL_RE = re.compile(r"https?://[^\s<>\"'）)】]+", re.IGNORECASE)
SEARCH_CUE = re.compile(
    r"(帮我查|查一下|查查|搜一下|搜搜|搜下|搜索一下|百度一下|"
    r"最新|新闻|现在.{0,6}(多少钱|什么价|怎么样)|今天.{0,4}(发生|新闻)|"
    r"是不是真的|有没有这回事)"
)
MAX_BYTES = 2_000_000
MAX_CHARS = 2200


def find_url(text: str) -> str | None:
    match = URL_RE.search(text or "")
    return match.group(0).rstrip(".,;!?，。；！？") if match else None


def wants_search(text: str) -> bool:
    return bool(text) and len(text) <= 120 and bool(SEARCH_CUE.search(text))


def _safe_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except Exception:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    return True


def _get(url: str, timeout: float = 8.0) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("unsupported url")
    if not _safe_host(parsed.hostname):
        raise ValueError("private target refused")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(MAX_BYTES)


def _text_of(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        html = html.replace(entity, char)
    return re.sub(r"\s+", " ", html).strip()


def fetch_page(url: str, timeout: float = 8.0) -> dict | None:
    try:
        raw = _get(url, timeout=timeout)
    except Exception:
        return None
    charset = "utf-8"
    match = re.search(rb'charset=["\']?([\w-]+)', raw[:4000], re.I)
    if match:
        charset = match.group(1).decode("ascii", "ignore")
    try:
        html = raw.decode(charset, "replace")
    except Exception:
        html = raw.decode("utf-8", "replace")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = _text_of(title_match.group(1))[:120] if title_match else ""
    text = _text_of(html)[:MAX_CHARS]
    return {"title": title, "url": url, "text": text}


def search(query: str, limit: int = 4, timeout: float = 8.0) -> list[dict]:
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=zh-CN"
    try:
        html = _get(url, timeout=timeout).decode("utf-8", "replace")
    except Exception:
        return []
    results = []
    for block in re.findall(r'(?s)<li class="b_algo".*?</li>', html):
        match = re.search(r'(?s)<h2>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not match:
            continue
        snippet = re.search(r'(?s)<p[^>]*>(.*?)</p>', block)
        results.append({
            "url": match.group(1),
            "title": _text_of(match.group(2))[:90],
            "snippet": (_text_of(snippet.group(1)) if snippet else "")[:160],
        })
        if len(results) >= limit:
            break
    return results