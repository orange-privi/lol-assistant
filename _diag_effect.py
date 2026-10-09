"""Diagnose why most summoner-spell `effect`s are empty."""
import io
import sys

sys.path.insert(0, ".")
from src.parser.wiki_lua import parse_lua  # noqa: E402
from src.parser.wiki_summoner import (  # noqa: E402
    clean_rendered_html,
    normalize_wiki_templates,
)

en = parse_lua(io.open("raw/16.20/zh_CN/wiki/SpellData_data.lua", encoding="utf-8").read())
zh = parse_lua(io.open("raw/16.20/zh_CN/wiki/SpellData_data_zh.lua", encoding="utf-8").read())
en = en if isinstance(en, dict) else {}
zh = zh if isinstance(zh, dict) else {}

print("en keys:", len(en), "zh keys:", len(zh))

for key in ["Smite", "Flash", "Heal", "Barrier", "Blasting Smite"]:
    e = en.get(key) or {}
    z = zh.get(key) or {}
    print("\n==", key)
    print("   en.effect:", repr((e.get("effect") or "")[:220]))
    print("   zh.effect:", repr((z.get("effect") or "")[:220]))

# Render one templated effect through the live wiki parser
import requests  # noqa: E402

src = (en.get("Smite") or {}).get("effect") or ""
print("\n--- render test ---")
print("input:", repr(src[:200]))
try:
    r = requests.post(
        "https://wiki.leagueoflegends.com/en-us/api.php",
        data={
            "action": "parse",
            "contentmodel": "wikitext",
            "text": normalize_wiki_templates(src),
            "prop": "text",
            "format": "json",
            "disablelimitreport": "1",
        },
        headers={"User-Agent": "lol-assistant-data/1.0"},
        timeout=60,
    )
    print("HTTP", r.status_code, "bytes", len(r.content))
    js = r.json()
    if "error" in js:
        print("API ERROR:", js["error"])
    html = ((js.get("parse") or {}).get("text") or {})
    html = html.get("*") if isinstance(html, dict) else None
    print("rendered html:", repr((html or "")[:300]))
    print("cleaned:", repr(clean_rendered_html(html or "")[:300]))
except Exception as exc:  # noqa: BLE001
    print("RENDER EXC:", type(exc).__name__, exc)
