"""从设备端 APK 提取真实应用名（label）与启动图标，并做本地缓存。

Android 的 shell 接口（pm / cmd package）拿不到 application label 和 icon，
唯一可靠来源是 APK 内的二进制 AndroidManifest.xml + resources.arsc。
本模块用 pyaxmlparser 解析，两条取数路径：

* 轻量路径：设备支持 `unzip -p` 时，只取 AndroidManifest.xml / resources.arsc /
  图标文件（通常合计 < 1 MB），避免把几十 MB 的整包拉回电脑；
* 回退路径：`adb pull` 整包再解析，解析完立刻删除临时 APK。

缓存目录只保留小体积的图标 PNG 与 meta.json，按「APK 路径」做 key，
应用更新后路径变化会自动重新提取。所有函数都是同步阻塞的，由调用方放进线程池。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .paths import ADB

CACHE_DIR = Path.home() / "Library/Application Support/ScrcpyStudio/appinfo"
ICON_DIR = CACHE_DIR / "icons"
META_PATH = CACHE_DIR / "meta.json"

_LOCK = threading.Lock()
_MAX_APK_BYTES = 220 * 1024 * 1024   # 超过这个体积的整包跳过（多为大型游戏）
_ICON_RE = re.compile(r"(ic_launcher|ic_icon|app_icon|icon|logo).*\.(png|webp|jpg)$", re.I)
_DPI_RANK = ("xxxhdpi", "xxhdpi", "xhdpi", "hdpi", "mdpi", "ldpi", "anydpi")


@dataclass
class AppInfo:
    package: str
    label: str = ""
    icon: str = ""            # 本地缓存 PNG 的绝对路径，空表示未取到
    source: str = ""          # light / full / cache / fallback

    @property
    def usable(self) -> bool:
        return bool(self.label or self.icon)


# ---------- 缓存 ----------

def _read_meta() -> dict[str, dict]:
    try:
        return json.loads(META_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_meta(meta: dict[str, dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(META_PATH)


def cached_info(package: str, key: str) -> AppInfo | None:
    entry = _read_meta().get(package)
    if not entry or entry.get("key") != key:
        return None
    icon = entry.get("icon", "")
    if icon and not Path(icon).exists():
        return None
    return AppInfo(package, entry.get("label", ""), icon, "cache")


def all_cached() -> dict[str, AppInfo]:
    result: dict[str, AppInfo] = {}
    for pkg, entry in _read_meta().items():
        icon = entry.get("icon", "")
        if icon and not Path(icon).exists():
            icon = ""
        result[pkg] = AppInfo(pkg, entry.get("label", ""), icon, "cache")
    return result


def invalidate(package: str | None = None) -> None:
    with _LOCK:
        meta = _read_meta()
        if package is None:
            meta = {}
        else:
            meta.pop(package, None)
        _write_meta(meta)


def cache_size() -> int:
    return sum(p.stat().st_size for p in ICON_DIR.glob("*") if p.is_file()) if ICON_DIR.exists() else 0


# ---------- adb 原始二进制 ----------

def _binary(args: list[str], timeout: int = 90) -> bytes:
    """adb 输出二进制时不能用 adb.run()（它会按文本解码）。"""
    try:
        proc = subprocess.run([ADB, *args], capture_output=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return b""
    if proc.returncode != 0:
        return b""
    return proc.stdout


def _shell_text(serial: str, command: str, timeout: int = 25) -> str:
    try:
        proc = subprocess.run(
            [ADB, "-s", serial, "shell", command],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "").strip()


def apk_path(serial: str, package: str) -> str:
    out = _shell_text(serial, f"pm path {package}")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("package:")]
    paths = [ln[len("package:"):].strip() for ln in lines]
    for path in paths:
        if path.endswith("base.apk"):
            return path
    return paths[0] if paths else ""


def _apk_key(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]


def _size_of(serial: str, path: str) -> int:
    out = _shell_text(serial, f"stat -c %s '{path}'", timeout=15)
    try:
        return int(out.splitlines()[0])
    except (ValueError, IndexError):
        return 0


# ---------- APK 解析 ----------

def _mini_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def _parse_label_and_icon(raw: bytes) -> tuple[str, str]:
    """从（可能是精简过的）APK 字节里解析 label 与图标在 zip 内的路径。"""
    from pyaxmlparser import APK

    apk = APK(raw, raw=True)
    try:
        label = apk.get_app_name() or ""
    except Exception:  # noqa: BLE001 - 第三方解析器对残缺 APK 会抛各种异常
        label = ""
    if label.startswith("0x") or label.startswith("@"):
        label = ""      # 只拿到资源 ID，说明 resources.arsc 没解析成功
    try:
        icon_path = apk.get_app_icon() or ""
    except Exception:  # noqa: BLE001
        icon_path = ""
    return label.strip(), icon_path


def _pick_fallback_icon(names: list[str]) -> str:
    """adaptive icon 常是 XML，退而求其次找一张现成的 PNG/WebP。"""
    candidates = [n for n in names if _ICON_RE.search(n) and not n.endswith(".xml")]
    if not candidates:
        return ""

    def rank(name: str) -> tuple[int, int]:
        for i, dpi in enumerate(_DPI_RANK):
            if dpi in name.lower():
                return (i, len(name))
        return (len(_DPI_RANK), len(name))

    return sorted(candidates, key=rank)[0]


def _unzip_entry(serial: str, path: str, entry: str, timeout: int = 45) -> bytes:
    return _binary(
        ["-s", serial, "exec-out", f"unzip -p '{path}' '{entry}'"], timeout=timeout,
    )


def _light_fetch(serial: str, path: str) -> tuple[str, bytes] | None:
    """只拉 manifest / resources.arsc / 图标，返回 (label, 图标字节)。"""
    manifest = _unzip_entry(serial, path, "AndroidManifest.xml")
    if len(manifest) < 64:
        return None                      # 设备没有可用的 unzip -p
    arsc = _unzip_entry(serial, path, "resources.arsc")
    mini = _mini_zip({"AndroidManifest.xml": manifest, "resources.arsc": arsc} if arsc
                     else {"AndroidManifest.xml": manifest})
    try:
        label, icon_path = _parse_label_and_icon(mini)
    except Exception:  # noqa: BLE001
        return None
    if not icon_path:
        return (label, b"") if label else None
    if icon_path.endswith(".xml"):
        names = _shell_text(serial, f"unzip -Z1 '{path}'", timeout=30).splitlines()
        icon_path = _pick_fallback_icon(names)
        if not icon_path:
            return (label, b"") if label else None
    icon = _unzip_entry(serial, path, icon_path)
    return label, icon if len(icon) > 64 else b""


def _full_fetch(serial: str, path: str, key: str) -> tuple[str, bytes] | None:
    size = _size_of(serial, path)
    if size and size > _MAX_APK_BYTES:
        return None
    tmp = CACHE_DIR / f"_tmp_{key}.apk"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [ADB, "-s", serial, "pull", path, str(tmp)],
            capture_output=True, timeout=180,
        )
        if proc.returncode != 0 or not tmp.exists():
            return None
        raw = tmp.read_bytes()
        label, icon_path = _parse_label_and_icon(raw)
        icon = b""
        try:
            from pyaxmlparser import APK

            apk = APK(raw, raw=True)
            if icon_path and not icon_path.endswith(".xml"):
                try:
                    icon = apk.get_file(icon_path)
                except Exception:  # noqa: BLE001
                    icon = b""
            if not icon:
                fallback = _pick_fallback_icon(apk.zip.namelist())
                if fallback:
                    icon = apk.get_file(fallback)
        except Exception:  # noqa: BLE001
            pass
        return label, icon
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        tmp.unlink(missing_ok=True)


def fetch(serial: str, package: str, force: bool = False) -> AppInfo:
    """取一个应用的真实名称与图标；结果写入缓存。"""
    path = apk_path(serial, package)
    if not path:
        return AppInfo(package)
    apk_size = _size_of(serial, path)
    key = _apk_key(path) + (f"-{apk_size}" if apk_size else "")

    if not force:
        hit = cached_info(package, key)
        if hit:
            return hit

    result = None
    source = "fallback"
    try:
        result = _light_fetch(serial, path)
        if result:
            source = "light"
    except Exception:  # noqa: BLE001 - 任何失败都退回整包
        result = None
    if not result:
        result = _full_fetch(serial, path, _apk_key(path))
        if result:
            source = "full"

    label = result[0] if result else ""
    icon_bytes = result[1] if result else b""
    icon_file = ""
    if icon_bytes and _valid_image(icon_bytes):
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        icon_file = str(ICON_DIR / f"{package.replace('.', '_')}_{_apk_key(path)}.png")
        Path(icon_file).write_bytes(icon_bytes)

    with _LOCK:
        meta = _read_meta()
        meta[package] = {"key": key, "label": label, "icon": icon_file}
        _write_meta(meta)
    return AppInfo(package, label, icon_file, source)


def _valid_image(data: bytes) -> bool:
    return (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))
