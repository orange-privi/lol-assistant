from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 技能官方文案（客户端字符串表）
#
# ## 为什么需要它
#
# Data Dragon 的被动（P）只给一句**不含任何数字**的 prose
# （`孙悟空在与英雄或野怪战斗时，会获得可叠加的护甲和最大生命值回复。`），
# 而 Q/W/E/R 的 tooltip 自带 `{{ 占位符 }}`。于是被动在客户端只能读到
# `dataValuesJson` 里那串**引擎内部字段名**（`Combat Duration` / `Stack Multiplier` /
# `Tooltip Max Health Percent Per5` …）—— 这正是「数值没归一化」的根源。
#
# 官方**带数值的**完整描述是存在的，只是不在 Data Dragon，而在客户端字符串表里。
# 同一个技能可能有好几处写法，按可靠性排序（数字越小越优先）。
# 之所以要显式定序而不是「谁先被读到算谁」：字符串表是按字母序排的，
# `game_buff_tooltip_*` 恰好排在 `generatedtip_*` 与 `spell_*` 前面，
# 靠读入顺序会让「这个单位被击晕了。」这种**状态描述**盖掉真正的技能描述。
_PRIORITY_SPELL = 0   # spell_<script>_tooltip          技能面板正文
_PRIORITY_TIP = 1     # generatedtip_*_<script>_tooltip  客户端悬停提示
_PRIORITY_GAME = 2    # game_(buff|spell)_tooltip_<script> 增益/技能面板（最次）

# 该脚本一条正文都取不到时用的优先级（排在所有真实来源之后）。
_NO_BODY = 99

# ## 两条硬约定
#
# 1. **占位符语法是 `@`，不是 `{{ }}`**：本模块原样保留，交由客户端渲染器填值
#    （Android 侧 `SpellNumbers`）。ETL 不在这里求值 —— 求值要复刻整套公式解释器，
#    而客户端已经有一份经实测的。
# 2. **只清纯装饰的东西**：`%i:scaleAP%` 图标标记、`{{Spell_X_Tooltip}}` 模板包含标记、
#    空的成对标记（`<spellName> </spellName>`，真值由客户端运行时填入）、HTML 实体。
#    **客户端标记（`<scaleArmor>` / `<keywordMajor>` / `<healing>` …）一律保留**
#    —— 它们是界面分色的唯一依据，剥掉了技能描述就少一层信息。
# ---------------------------------------------------------------------------

# 技能键：脚本名小写。备选后缀按长度倒序，避免 `tooltip` 抢 `tooltipextended` 的前缀。
_SPELL_KEY = re.compile(
    r"^spell_(.+?)_(tooltipextended|tooltipsimple|tooltip|summary|name)$"
)

# 增益 / 技能面板键：`game_buff_tooltip_kalistapassivebuff`。
_GAME_KEY = re.compile(r"^game_(?:buff|spell)_tooltip_(.+)$")

# 悬停提示键：`generatedtip_passive_akalip_tooltip` / `generatedtip_spell_aatroxq_tooltip`。
_GENERATED_KEY = re.compile(r"^generatedtip_(?:passive|spell)_(.+?)_tooltip$")

_MAIN_TEXT = re.compile(r"<mainText>(.*?)</mainText>", re.IGNORECASE | re.DOTALL)

_TITLE_LEFT = re.compile(r"<titleLeft>(.*?)</titleLeft>", re.IGNORECASE | re.DOTALL)

# `{{Spell_AkaliP_Tooltip}}` / `{{ game_spell_Kayn_P_main_@f1@ }}`：模板包含标记，不是内容。
_TEMPLATE_REF = re.compile(r"\{\{.*?\}\}")

# `%i:scaleAP%` / `%i:cooldown%`：纯图标标记，剥掉后句子照样读得通。
_ICON_MARKER = re.compile(r"%i:[A-Za-z0-9_]+%")

# 客户端标记里表示「此处插入一段额外加成说明」的占位符：它不是数值，没有也不该算缺项。
MODIFIER_APPEND = "SpellModifierDescriptionAppend"

# `@HealthPercentPer5@` / `@HealthPercentPer5*100@`：数值占位符。这是**唯一**的判据来源 ——
# 只有正文里真的留着能填的占位符，这一列才有存在意义（见 `token_names`）。
VALUE_TOKEN = re.compile(
    r"@(?!SpellModifierDescriptionAppend@)"
    r"[A-Za-z0-9_]+(?:\s*[*/]\s*-?\d+(?:\.\d+)?)?@"
)

# `<spellName> </spellName>`：成对但内容为空的标记，真值由客户端运行时填入
# （「爆头对被<spellName> </spellName>和<spellName> </spellName>影响的敌人们…」）。
# 留一对空标记只会多出空格，整块清掉。
_EMPTY_TAG_PAIR = re.compile(r"<([A-Za-z0-9_]+)>[\s\r\n]*</\1>")

_MULTI_SPACE = re.compile(r"[ \t]{2,}")

_ENTITIES = (
    ("&nbsp;", " "),
    ("&amp;", "&"),
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&quot;", '"'),
    ("&#39;", "'"),
)

# 同一份字符串表里并存着「国服/典藏」变体（脚本名带 `jade` / `ruby` 前后缀）。
# 脚本名直查命中的就是正式版，所以**只把它当排序偏好**（正式版在前），不整个过滤掉 ——
# 有些技能（崔斯特、基兰的被动）只存在变体，过滤了就等于什么都没有。
_VARIANT = re.compile(r"(^|_)(jade|ruby)(_|$)")


def _normalize_label(value: str) -> str:
    """技能名归一：`&nbsp;` / 不间断空格 / 首尾空白都折平，用于按名反查。"""
    text = value or ""
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    return text.replace("\u00a0", " ").strip()


class SpellTextIndex:
    """`lol.stringtable.json` 的 `entries` -> 技能官方文案索引（只读、纯内存）。

    索引三种查法，按可靠性排序：

    1. **脚本名直查**（主）：脚本名来自 CommunityDragon BIN 的对象路径叶名
       （`Characters/MonkeyKing/Spells/MonkeyKingPassiveAbility/MonkeyKingPassive`
       → `MonkeyKingPassive`），是最精确的键。
    2. **本地化技能名反查**（兜底）：补丁之间脚本名会改
       （`AatroxPassive` ↔ `AatroxP`、`CaitlynP` ↔ `CaitlynPassive`），
       直查落空时用 Data Dragon 的技能名（`赐死剑气` / `爆头`）反查脚本名；
       传了 `champion_id` 时**优先本英雄的脚本**（脚本名通常以英雄 id 打头），
       避免同名技能（「誓约者」这类）串到别的英雄。
    3. **`name` 键**（构建反查表用）：`spell_<script>_name`、
       `game_*`/`generatedtip_*` 的 `<titleLeft>` 都是本地化技能名，三边都收。
    """

    def __init__(self, entries: dict[str, Any] | None = None):
        # script -> [(priority, raw)]，取值时按 priority 升序试
        self._bodies: dict[str, list[tuple[int, str]]] = {}
        self._by_name: dict[str, list[str]] = {}
        self._priority_cache: dict[str, int] = {}

        for key, value in (entries or {}).items():
            if not isinstance(key, str) or not isinstance(value, str) or not value:
                continue

            match = _SPELL_KEY.match(key)
            if match:
                script, kind = match.group(1).lower(), match.group(2)
                if kind == "tooltip":
                    self._add_body(script, value, _PRIORITY_SPELL)
                elif kind == "name":
                    self._index_name(value, script)
                continue

            match = _GAME_KEY.match(key)
            if match:
                script = match.group(1).lower()
                self._add_body(script, main_text(value), _PRIORITY_GAME)
                title = title_left(value)
                if title:
                    self._index_name(title, script)
                continue

            match = _GENERATED_KEY.match(key)
            if match:
                script = match.group(1).lower()
                self._add_body(script, main_text(value), _PRIORITY_TIP)
                title = title_left(value)
                if title:
                    self._index_name(title, script)

    # -- 查询 ---------------------------------------------------------------

    def is_usable(self) -> bool:
        """字符串表是否可用。缺失/损坏时索引为空，调用方据此整块降级。"""
        return bool(self._bodies)

    def tooltip_for(
        self,
        scripts: Iterable[str],
        localized_name: str = "",
        champion_id: str = "",
    ) -> str:
        """取一个技能的官方正文；取不到返回空串（**不编造**）。

        `scripts` 是候选脚本名，先到先得 —— 调用方应把最可靠的放前面
        （BIN 匹配到的对象叶名）。每个脚本再按自身候选正文逐条试：
        正文清洗后为空（例如整段只是个取不到的模板包含）就换下一条。
        `localized_name` 是 Data Dragon 的技能名，仅在直查全部落空时启用，
        用来兜住补丁间的脚本改名。
        """
        for script in self._ranked(scripts, self._best_priority, champion_id):
            text = self._text_of(script)
            if text:
                return text

        name = _normalize_label(localized_name)
        if name:
            candidates = self._by_name.get(name, ())
            for script in self._ranked(candidates, self._best_priority, champion_id):
                text = self._text_of(script)
                if text:
                    return text

        return ""

    # -- 内部 ---------------------------------------------------------------

    def _text_of(self, script: str) -> str:
        bucket = self._bodies.get((script or "").lower(), ())
        for _, raw in sorted(bucket, key=lambda item: item[0]):
            text = clean_official_text(raw)
            if text:
                return text
        return ""

    def _best_priority(self, script: str) -> int:
        """该脚本**实际取得到正文**的最高优先级；取不到给一个大值。

        判据要按「清洗后是否还有字」算，而不是「有没有这个键」——
        `spell_kaynpassive_tooltip` 确实存在，但正文整段只是个取不到的模板包含，
        算它可用会把后面真正有内容的候选挤掉。
        """
        cached = self._priority_cache.get(script)
        if cached is not None:
            return cached
        best = _NO_BODY
        for priority, raw in self._bodies.get((script or "").lower(), ()):
            if clean_official_text(raw):
                best = min(best, priority)
        self._priority_cache[script] = best
        return best

    def _add_body(self, script: str, raw: str, priority: int) -> None:
        """登记一条候选正文。空的（`<mainText></mainText>` 这种）直接跳过。"""
        if not script or not raw:
            return
        bucket = self._bodies.setdefault(script, [])
        if all(raw != existing for _, existing in bucket):
            bucket.append((priority, raw))

    def _index_name(self, value: str, script: str) -> None:
        name = _normalize_label(value)
        if not name:
            return
        bucket = self._by_name.setdefault(name, [])
        if script not in bucket:
            bucket.append(script)

    @staticmethod
    def _ranked(
        scripts: Iterable[str], best_priority, champion_prefix: str
    ) -> list[str]:
        """候选脚本排序：来源可靠性 → 正式版在变体之前 → 本英雄的在前。

        三项都是必需的，且**顺序不能换**：

        1. **来源可靠性**（`spell_*` > `generatedtip_*` > `game_*`）必须第一。
           按名反查会命中一串脚本，其中既有真正描述技能的，也有描述**单位身上的状态**
           的（`game_buff_tooltip_ashepassiveneutraldebuff` →
           「这个单位会受到来自艾希的额外伤害。」）。不排就会让后者先命中。
        2. **变体偏好**必须排在英雄前缀**之前**。`_jade` / `_ruby` 是同一技能的
           另一份文案，正式版应当在前；而变体脚本名恰好都以英雄 id 打头
           （`jannapassive_jade`），英雄的**正式**脚本名却常常不以
           （`tailwindself` / `voidstone` / `backstab`）。若把英雄前缀放在前面，
           这一项就会被绕过，反把变体选出来。
        3. **英雄前缀**只是兜底：同名技能跨英雄时优先本英雄的。它是启发式
           （对 `tailwindself` 这类脚本名必然误判），所以排在最后。
        """
        prefix = (champion_prefix or "").lower()

        def weight(script: str) -> tuple[int, int, int]:
            low = (script or "").lower()
            belongs = 0 if prefix and low.startswith(prefix) else 1
            return (
                best_priority(script),
                1 if _VARIANT.search(low) else 0,
                belongs,
            )

        return sorted(scripts, key=weight)


def main_text(raw: str) -> str:
    """从分区化的工具提示里抽出 `<mainText>` 正文。

    抽不到就返回空串 —— **不能退回整段**：外面还挂着 `<titleLeft>`（技能名）、
    `<titleRight>`（冷却）、`<postScriptLeft>` 等分区，整段塞进正文会让技能名
    在卡片上重复出现。

    公开给野怪模块复用：野怪的 `enemytooltip` 也是同一套分区结构。
    """
    match = _MAIN_TEXT.search(raw or "")
    return match.group(1) if match else ""


def title_left(raw: str) -> str:
    """抽 `<titleLeft>`（本地化名）——可能带嵌套标记，调用方按需剥。"""
    match = _TITLE_LEFT.search(raw or "")
    return match.group(1) if match else ""


def clean_official_text(body: str) -> str:
    """官方正文 -> 可交给客户端渲染器的文本。

    只做**无损**的事：清模板包含标记、清图标标记、清空的成对标记、解 HTML 实体、
    折平空白。客户端标记与 `@占位符@` 原样保留（见模块头「两条硬约定」）。
    """
    if not body:
        return ""
    text = _TEMPLATE_REF.sub("", body)
    text = _ICON_MARKER.sub("", text)
    text = _EMPTY_TAG_PAIR.sub("", text)
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    return _MULTI_SPACE.sub(" ", text.replace("\u00a0", " ")).strip()


def token_names(text: str) -> set[str]:
    """正文里出现的数值占位符名（小写）。

    供调用方判断「这段文本能不能真的填出数」—— 文本本身没有可填的占位符时，
    它与 Data Dragon 那句 prose 等价，这一列就不该有值（见 `pipeline.render_spell_text`）。
    """
    names: set[str] = set()
    for match in VALUE_TOKEN.finditer(text or ""):
        name = match.group(0)[1:-1]
        for op in ("*", "/"):
            at = name.find(op)
            if at > 0:
                name = name[:at]
                break
        name = name.strip().lower()
        if name:
            names.add(name)
    return names


def official_tooltip(
    index: SpellTextIndex,
    scripts: Iterable[str],
    localized_name: str = "",
    champion_id: str = "",
) -> str:
    """给一个技能取官方文案并清洗；取不到返回空串。

    调用方**只应在 Data Dragon 填不出数值时**调用（判据见 `pipeline` 的
    `render_spell_text`）：Q/W/E/R 的 tooltip 自带 `{{ 占位符 }}`，客户端那条路径
    已经能渲染，再叠一层反而多一份要维护的文本。
    """
    if index is None or not index.is_usable():
        return ""
    return index.tooltip_for(scripts, localized_name, champion_id)
