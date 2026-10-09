import re
import requests

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
CD = "https://raw.communitydragon.org/latest"

r = requests.get(f"{CD}/game/data/characters/", headers=BROWSER_UA, timeout=60)
html = r.text
# Directory listings from raw.communitydragon.org are simple <a href="...">…
links = sorted(set(re.findall(r'href="([^"]+)"', html)))
dirs = [l for l in links if l.endswith("/")]
sru = [d for d in dirs if d.startswith("sru")]
print("total links:", len(links), "dirs:", len(dirs))
print("\n-- sru_* dirs (%d) --" % len(sru))
print(sru)
other = [d for d in dirs if not d.startswith("sru")]
print("\n-- non-sru sample (%d) --" % len(other))
print(other[:80])
