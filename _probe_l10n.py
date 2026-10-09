import re
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
CD = "https://raw.communitydragon.org/latest"


def head(url):
    try:
        r = requests.get(url, headers=BROWSER_UA, timeout=30)
        return r.status_code, len(r.content)
    except Exception as exc:  # noqa: BLE001
        return "ERR", str(exc)[:100]


def listdir(url):
    r = requests.get(url, headers=BROWSER_UA, timeout=60)
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
    return [l for l in links if not l.startswith(("/", "..", "http", "?"))]


print("== localized bin? ==")
for u in [
    f"{CD}/game/zh_cn/data/characters/sru_baron/sru_baron.bin.json",
    f"{CD}/game/zh_cn/data/characters/sru_baron/",
    f"{CD}/game/en_us/data/characters/sru_baron/",
]:
    print(head(u), u)

print("\n== game locale root listing ==")
print(listdir(f"{CD}/game/zh_cn/")[:30])
print(listdir(f"{CD}/game/zh_cn/data/")[:30])

print("\n== plugins localized v1 for monsters/maps ==")
for u in [
    f"{CD}/plugins/rcp-be-lol-game-data/global/zh_cn/v1/",
    f"{CD}/plugins/rcp-be-lol-game-data/global/default/v1/",
]:
    print(u, "->", listdir(u))

print("\n== datadragon monster-ish? ==")
for u in [
    "https://ddragon.leagueoflegends.com/cdn/16.20.1/data/zh_CN/champion.json",
]:
    print(head(u), u)

print("\n== search CDragon for localized name files (menu) ==")
for u in [
    f"{CD}/game/zh_cn/data/menu/",
    f"{CD}/game/en_us/data/menu/",
]:
    print(u, "->", listdir(u)[:40])
