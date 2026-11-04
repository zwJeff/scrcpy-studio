"""按应用类型对包名分组。

匹配优先级：用户自定义覆盖 → 精确包名 → 关键词规则 → 系统应用 → 其他。
规则全部基于包名（小写）子串，避免依赖设备端读不到的应用 label。
"""
from __future__ import annotations

# (key, 显示名, 主题色) —— 顺序即界面上的展示顺序
CATEGORIES: list[tuple[str, str, str]] = [
    ("social", "社交", "#4C8BF5"),
    ("media", "影音", "#E8756B"),
    ("game", "游戏", "#A56BE0"),
    ("shopping", "购物", "#E5943C"),
    ("finance", "金融", "#3FA47C"),
    ("smart_home", "智能家居", "#3FA7B5"),
    ("travel", "出行", "#5B8FD9"),
    ("reading", "阅读", "#C2785C"),
    ("photo", "摄影", "#D2749E"),
    ("office", "办公", "#6C86C9"),
    ("health", "健康运动", "#63A75C"),
    ("education", "教育", "#9A80C8"),
    ("tools", "工具", "#7C8896"),
    ("system", "系统", "#9A9A94"),
    ("other", "其他", "#A8A49B"),
]

CATEGORY_LABEL = {key: label for key, label, _ in CATEGORIES}
CATEGORY_COLOR = {key: color for key, _, color in CATEGORIES}
CATEGORY_ORDER = [key for key, _, _ in CATEGORIES]

# 精确包名 → 分类（覆盖关键词规则，处理包名不含语义的常见应用）
EXACT: dict[str, str] = {
    "com.tencent.mm": "social", "com.tencent.mobileqq": "social",
    "com.tencent.wework": "office", "com.tencent.tim": "social",
    "com.tencent.qqlive": "media", "com.tencent.qqmusic": "media",
    "com.tencent.mtt": "tools", "com.tencent.weread": "reading",
    "com.tencent.qqmail": "office", "com.ss.android.ugc.aweme": "media",
    "com.ss.android.ugc.aweme.lite": "media", "com.ss.android.article.news": "reading",
    "com.ss.android.lark": "office", "com.smile.gifmaker": "media",
    "com.xingin.xhs": "social", "tv.danmaku.bili": "media",
    "com.zhihu.android": "reading", "com.sina.weibo": "social",
    "com.taobao.taobao": "shopping", "com.tmall.wireless": "shopping",
    "com.jingdong.app.mall": "shopping", "com.xunmeng.pinduoduo": "shopping",
    "com.eg.android.AlipayGphone": "finance", "com.unionpay": "finance",
    "com.achievo.vipshop": "shopping", "com.sankuai.meituan": "shopping",
    "com.dianping.v1": "shopping", "me.ele": "shopping",
    "com.alibaba.android.rimet": "office", "com.alibaba.idlefish": "shopping",
    "com.autonavi.minimap": "travel", "com.baidu.BaiduMap": "travel",
    "com.baidu.searchbox": "tools", "com.quark.browser": "tools",
    "com.UCMobile": "tools", "com.sdu.didi.psnger": "travel",
    "com.netease.cloudmusic": "media", "com.kugou.android": "media",
    "com.qiyi.video": "media", "com.youku.phone": "media",
    "com.mgtv.mobile.tv": "media", "com.sohu.sohuvideo": "media",
    "com.babytree.www.babytree": "health", "com.gotokeep.keep": "health",
    "com.miui.health": "health", "com.huawei.health": "health",
    "com.miui.home": "system", "com.android.settings": "system",
    "com.android.chrome": "tools", "com.android.camera": "photo",
    "com.android.gallery3d": "photo", "com.android.deskclock": "tools",
    "com.android.mms": "social", "com.android.contacts": "social",
    "com.android.dialer": "social", "com.google.android.gms": "system",
    "com.miui.smartHome": "smart_home", "com.miui.smarthome": "smart_home",
}

# (分类, 关键词) —— 命中任一关键词即归入该分类；按表中顺序匹配
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("smart_home", ("smarthome", "smart_home", "iot", "mi.home", "mijia", "tuya",
                    "smartlife", "aqara", "yeelight", "hass", "homeassistant",
                    "gree", "haier", "hisense", "philips.hue", "echonet")),
    ("finance", ("bank", "pay", "wallet", "finance", "stock", "broker", "fund",
                 "insurance", "credit", "cmb", "icbc", "ccb", "boc.", "abc.",
                 "alipay", "unionpay", "jijin", "licai", "zqsb", "hexun")),
    ("shopping", ("shop", "mall", "taobao", "jd.", "jingdong", "pinduoduo",
                  "suning", "vipshop", "kaola", "meituan", "eleme", "dianping",
                  "xiansheng", "fresh", "store", "deals", "coupon", "waimai")),
    ("game", ("game", "gamer", "taptap", "miHoYo", "mihoyo", "tencent.tmgp",
              "tencent.mg", "netease.game", "lilith", "habby", "supercell",
              "unity3d", "epic", "riot", "playstation", "nintendo", "steam",
              "battle", "puzzle", "idle", "gacha", "arena")),
    ("media", ("video", "music", "player", "radio", "podcast", "live", "tv.",
               ".tv.", "movie", "cinema", "anime", "bilibili", "douyin",
               "kuaishou", "kugou", "qqmusic", "netease.cloud", "iqiyi",
               "youku", "mgtv", "douban.fm", "ximalaya", "ting.", "fm.",
               "shortvideo", "media", "stream")),
    ("social", ("wechat", "weixin", "qq", "chat", "im.", "messenger", "social",
                "weibo", "moments", "sns", "tweet", "twitter", "telegram",
                "whatsapp", "discord", "slack", "momo", "soul", "tanTan",
                "zhihu", "tieba", "forum", "community", "xiaohongshu")),
    ("travel", ("map", "navigation", "navi", "taxi", "didi", "uber", "ride",
                "trip", "travel", "flight", "airline", "railway", "train",
                "rail", "bus", "metro", "traffic", "bike", "ofo", "mobike",
                "hellobike", "ctrip", "qunar", "booking", "amap", "baidumap")),
    ("reading", ("read", "book", "novel", "comic", "manga", "news", "magazine",
                 "article", "paper", "press", "jinri", "toutiao", "weread",
                 "kindle", "reader", "rss", "feed")),
    ("photo", ("camera", "photo", "gallery", "image", "edit.pic", "filter",
               "meitu", "beauty", "snapseed", "lightroom", "photoshop")),
    ("health", ("health", "fitness", "sport", "workout", "run.", "running",
                "pedometer", "sleep", "medical", "hospital", "doctor",
                "calorie", "yoga", "keep.", "mi.fit")),
    ("education", ("edu", "learn", "study", "school", "course", "课堂", "dict",
                   "translate", "language", "exam", "homework", "kid", "abc")),
    ("office", ("office", "doc", "sheet", "slide", "wps", "note", "memo",
                "calendar", "mail", "email", "drive", "cloud", "meeting",
                "dingtalk", "lark", "wework", "team", "task", "todo",
                "scan", "pdf", "print")),
    ("tools", ("browser", "chrome", "firefox", "search", "input", "keyboard",
               "launcher", "cleaner", "security", "antivirus", "vpn", "wifi",
               "filemanager", "file.manager", "explorer", "compress", "zip",
               "calculator", "clock", "weather", "compass", "flashlight",
               "recorder", "download", "transfer", "tool", "util")),
    ("system", ("android.", "com.android.", "com.google.android.", "com.miui.",
                "com.huawei.", "com.oppo.", "com.vivo.", "com.samsung.",
                "com.coloros.", "com.oneplus.", "com.mediatek.",
                "com.qualcomm.", "com.oem.")),
]

_SYSTEM_PREFIXES = (
    "android.", "com.android.", "com.google.android.", "com.miui.",
    "com.huawei.", "com.oppo.", "com.vivo.", "com.coloros.", "com.samsung.",
    "com.oneplus.", "com.mediatek.", "com.qualcomm.", "com.oem.",
)


def categorize(package: str, is_system: bool = False,
               overrides: dict[str, str] | None = None) -> str:
    """返回分类 key。overrides 来自用户自定义，优先级最高。"""
    pkg = package.lower()
    if overrides and package in overrides and overrides[package] in CATEGORY_LABEL:
        return overrides[package]
    if package in EXACT:
        return EXACT[package]
    for key, keywords in RULES:
        if any(word in pkg for word in keywords):
            return key
    if is_system or pkg.startswith(_SYSTEM_PREFIXES):
        return "system"
    return "other"


def label_of(key: str) -> str:
    return CATEGORY_LABEL.get(key, "其他")


def color_of(key: str) -> str:
    return CATEGORY_COLOR.get(key, "#A8A49B")


def group_packages(packages: list[str], system: set[str],
                   overrides: dict[str, str] | None = None) -> dict[str, list[str]]:
    """把包名按分类聚合，返回 {分类key: [包名...]}，只保留非空分类。"""
    grouped: dict[str, list[str]] = {}
    for pkg in packages:
        key = categorize(pkg, pkg in system, overrides)
        grouped.setdefault(key, []).append(pkg)
    return grouped
