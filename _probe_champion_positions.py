"""探针：核实客户端"分路位置"数据源的真实结构。

数据源（客户端选人界面分路筛选器的数据来源，非 ddragon）：
  https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-champion-statistics/
      global/default/rcp-fe-lol-champion-statistics.js

该 JS 是一个 webpack 打包产物，内嵌两段可用数据：
  1. JSON.parse('{...}')            -> { 位置: { 英雄key: 出场率 } }
  2. JADE_POSITIONS_BY_CHAMP_ID     -> { 英雄key: [位置, ...] }（新 ID 段 60001+）

本脚本只做读取与统计，不写入任何管线数据。
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import requests

URL = (
    "https://raw.communitydragon.org/latest/plugins/"
    "rcp-fe-lol-champion-statistics/global/default/"
    "rcp-fe-lol-champion-statistics.js"
)
DB = Path(__file__).parent / "output" / "lol-16.20.db"

POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
# 客户端内部用 SUPPORT；LCU / Riot API 用 UTILITY
CLIENT_TO_API = {"TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MIDDLE",
                 "BOTTOM": "BOTTOM", "SUPPORT": "UTILITY"}
ZH = {"TOP": "上路(上单)", "JUNGLE": "打野", "MIDDLE": "中路(中单)",
      "BOTTOM": "下路(射手)", "SUPPORT": "辅助"}


def fetch() -> str:
    resp = requests.get(
        URL,
        headers={"User-Agent": "lol-assistant-data/1.0",
                 "Accept": "*/*"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text


def _balanced_object(text: str, start: int) -> str | None:
    """从 ``text[start] == '{'`` 开始，按花括号配对截取一个完整 JSON 对象。

    压缩过的 JS 里 '}' 紧邻模块闭合花括号，正则很难稳妥切开，
    因此用配对计数而不是正则。
    """
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract(js: str) -> tuple[dict, dict]:
    """从压缩 JS 中取出两段数据。

    - 出场率那段的键是带引号的，本身就是合法 JSON。
    - ``JADE_POSITIONS_BY_CHAMP_ID`` 是 **JS 对象字面量**（数字键无引号：
      ``{60001:["MIDDLE"],...}``），必须先给键补上引号才能当成 JSON 解析。
    """
    play = re.search(r"JSON\.parse\('(\{.*?\})'\)", js, re.S)
    jade_raw = None
    marker = re.search(r"JADE_POSITIONS_BY_CHAMP_ID=(\{)", js)
    if marker:
        jade_raw = _balanced_object(js, marker.start(1))
    if jade_raw:
        jade_raw = re.sub(r"(\d+):", r'"\1":', jade_raw)
    return (
        json.loads(play.group(1)) if play else {},
        json.loads(jade_raw) if jade_raw else {},
    )


def main() -> None:
    js = fetch()
    print(f"JS 大小: {len(js):,} 字节")

    play, jade = extract(js)
    print(f"出场率数据包裹的位置: {list(play.keys())}")
    print(f"JADE 静态表英雄数: {len(jade)}")
    print()

    # -- 每分路的规模与出场率区间 --------------------------------------
    print(f"{'位置':<16}{'客户端键':<10}{'LCU键':<10}{'英雄数':>6}"
          f"{'最低':>9}{'最高':>9}")
    for pos in POSITIONS:
        rates = play.get(pos, {})
        vals = list(rates.values())
        print(f"{ZH[pos]:<14}{pos:<12}{CLIENT_TO_API[pos]:<10}"
              f"{len(vals):>6}{min(vals):>9.4%}{max(vals):>9.2%}")
    print()

    # -- 一个英雄能属于几个分路 ----------------------------------------
    by_champ: dict[str, list[tuple[str, float]]] = {}
    for pos, rates in play.items():
        for key, rate in rates.items():
            by_champ.setdefault(key, []).append((pos, rate))

    dist: dict[int, int] = {}
    for items in by_champ.values():
        dist[len(items)] = dist.get(len(items), 0) + 1
    print("单英雄覆盖分路数分布:",
          {k: v for k, v in sorted(dist.items())})
    print(f"出现在统计中的英雄总数: {len(by_champ)}")
    print()

    # -- 与本地库对齐，看多分路英雄的真实样子 --------------------------
    conn = sqlite3.connect(DB)
    name_of = {str(k): n for k, n in
               conn.execute("select key, name from champion")}
    multi = sorted(
        ((len(v), k, v) for k, v in by_champ.items()),
        reverse=True,
    )[:10]
    print("跨分路最多的 10 个英雄（本地库中文名）:")
    for n, key, items in multi:
        detail = "、".join(
            f"{ZH[p]}{r:.1%}" for p, r in
            sorted(items, key=lambda x: -x[1])
        )
        print(f"  {name_of.get(key, '?' + key):<8}{n}路  {detail}")
    print()

    # -- 本地库中有、但统计里没有分路数据的英雄 ------------------------
    missing = [n for k, n in name_of.items() if k not in by_champ]
    print(f"本地库 {len(name_of)} 个英雄中，统计里无任何分路的: {len(missing)}")
    print("  ", "、".join(missing[:20]) or "（无）")
    print()

    # -- JADE 静态表样例 ----------------------------------------------
    for key in list(jade)[:5]:
        print(f"  JADE {key}: {jade[key]}")


if __name__ == "__main__":
    main()
