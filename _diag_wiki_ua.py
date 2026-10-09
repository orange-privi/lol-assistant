import json
import time

import requests

WIKI = "https://wiki.leagueoflegends.com/en-us/api.php"

UAS = {
    "bot-simple": "lol-assistant-data/1.0",
    "bot-contact": "lol-assistant-data/1.0 (ETL; contact: dev@example.com)",
    "browser": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "curl": "curl/8.4.0",
    "wikibot": "lol-assistant-data-bot/1.0 (contact dev@example.com)",
}

frag = "Heals for {{as|600 true damage}} to the target."

for name, ua in UAS.items():
    for method in ("POST", "GET"):
        try:
            if method == "POST":
                r = requests.post(
                    WIKI,
                    data={
                        "action": "parse", "contentmodel": "wikitext",
                        "text": frag, "prop": "text", "format": "json",
                        "disablelimitreport": "1",
                    },
                    headers={"User-Agent": ua}, timeout=40,
                )
            else:
                r = requests.get(
                    WIKI,
                    params={
                        "action": "parse", "contentmodel": "wikitext",
                        "text": frag, "prop": "text", "format": "json",
                        "disablelimitreport": "1",
                    },
                    headers={"User-Agent": ua}, timeout=40,
                )
            ct = r.headers.get("content-type", "")
            ok = "json" in ct and r.status_code == 200
            detail = ""
            if ok:
                js = r.json()
                html = (js.get("parse") or {}).get("text") or {}
                detail = repr((html.get("*") if isinstance(html, dict) else "")[:120])
            print(f"{name:<12} {method:<5} HTTP {r.status_code} ct={ct[:30]:<30} {detail}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<12} {method:<5} EXC {type(exc).__name__}: {str(exc)[:80]}")
        time.sleep(0.3)

print("\n=== query API (GET) with bot-simple ===")
try:
    r = requests.get(
        WIKI,
        params={"action": "query", "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "format": "json",
                "titles": "Module:SpellData/data"},
        headers={"User-Agent": "lol-assistant-data/1.0"}, timeout=40,
    )
    print("HTTP", r.status_code, "ct", r.headers.get("content-type"), "len", len(r.content))
except Exception as exc:  # noqa: BLE001
    print("EXC", exc)
