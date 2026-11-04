"""adb 的薄封装：所有函数同步阻塞，由上层放到线程池执行。"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from .paths import ADB


class AdbError(RuntimeError):
    pass


def run(args: list[str], timeout: int = 25, serial: str | None = None) -> str:
    cmd = [ADB]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env={**__import__("os").environ, "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        raise AdbError(f"找不到 adb：{ADB}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb 命令超时：{' '.join(args)}") from exc
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and not out.strip():
        raise AdbError(f"adb 返回码 {proc.returncode}")
    return out


@dataclass
class Device:
    serial: str
    state: str
    model: str = ""
    product: str = ""
    usb: str = ""
    transport_id: str = ""

    @property
    def wireless(self) -> bool:
        return bool(re.match(r"^[\d.]+:\d+$", self.serial))

    @property
    def online(self) -> bool:
        return self.state == "device"

    @property
    def display_name(self) -> str:
        if self.model:
            return self.model.replace("_", " ")
        return self.serial.split(":")[0]

    @property
    def label(self) -> str:
        return "无线" if self.wireless else "USB"


def list_devices() -> list[Device]:
    out = run(["devices", "-l"], timeout=15)
    devices: list[Device] = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        dev = Device(serial=parts[0], state=parts[1])
        for token in parts[2:]:
            if ":" not in token:
                continue
            key, _, value = token.partition(":")
            if key == "model":
                dev.model = value
            elif key == "product":
                dev.product = value
            elif key == "usb":
                dev.usb = value
            elif key == "transport_id":
                dev.transport_id = value
        devices.append(dev)
    return devices


def mdns_services() -> list[tuple[str, str, str]]:
    """返回 [(服务名, 类型, 地址)]，地址形如 192.168.1.5:41235。"""
    try:
        out = run(["mdns", "services"], timeout=10)
    except AdbError:
        return []
    found: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of") or line.startswith("ERROR"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 3 and parts[2].count("."):
            found.append((parts[0], parts[1], parts[2]))
    return found


def connect(addr: str) -> str:
    return run(["connect", addr], timeout=20)


def disconnect(addr: str | None = None) -> str:
    return run(["disconnect"] + ([addr] if addr else []), timeout=15)


def pair(addr: str, code: str) -> str:
    return run(["pair", addr, code], timeout=30)


def tcpip(port: int = 5555) -> str:
    return run(["tcpip", str(port)], timeout=15)


def wlan_ip(serial: str) -> str:
    """取设备 Wi-Fi 地址，兼容 wlan0 / ap0 / 多网卡。"""
    try:
        out = run(["shell", "ip", "-f", "inet", "addr", "show"], serial=serial, timeout=15)
    except AdbError:
        return ""
    for line in out.splitlines():
        line = line.strip()
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/\d+", line)
        if not m:
            continue
        addr = m.group(1)
        if addr.startswith("127."):
            continue
        return addr
    return ""


@dataclass
class DeviceInfo:
    model: str = ""
    android: str = ""
    sdk: str = ""
    resolution: str = ""
    ip: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def device_info(serial: str) -> DeviceInfo:
    info = DeviceInfo()
    try:
        raw = run(
            ["shell", "getprop ro.product.model; getprop ro.build.version.release; "
                      "getprop ro.build.version.sdk; wm size | head -1"],
            serial=serial, timeout=15,
        )
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            info.model = lines[0]
        if len(lines) > 1:
            info.android = lines[1]
        if len(lines) > 2:
            info.sdk = lines[2]
        if len(lines) > 3:
            info.resolution = lines[3].split(":")[-1].strip()
    except AdbError:
        pass
    info.ip = wlan_ip(serial)
    return info


def list_apps(serial: str) -> list[tuple[str, str]]:
    """返回 [(包名, 启动 Activity)]，只保留带桌面入口的应用。"""
    apps: list[tuple[str, str]] = []
    try:
        out = run(
            ["shell", "cmd", "package", "query-activities", "--brief",
             "-a", "android.intent.action.MAIN",
             "-c", "android.intent.category.LAUNCHER"],
            serial=serial, timeout=40,
        )
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith(("Activity", "error", "Error", "Exception")):
                continue
            pkg, _, activity = line.partition("/")
            if pkg.count(".") >= 1 and " " not in pkg:
                apps.append((pkg, activity or ""))
    except AdbError:
        pass

    if not apps:
        try:
            out = run(["shell", "pm", "list", "packages", "-3"], serial=serial, timeout=40)
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    apps.append((line[8:].strip(), ""))
        except AdbError:
            pass

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for pkg, activity in apps:
        if pkg in seen:
            continue
        seen.add(pkg)
        unique.append((pkg, activity))
    return sorted(unique, key=lambda item: item[0])


def system_packages(serial: str) -> set[str]:
    try:
        out = run(["shell", "pm", "list", "packages", "-s"], serial=serial, timeout=40)
    except AdbError:
        return set()
    return {
        line.strip()[8:]
        for line in out.splitlines()
        if line.strip().startswith("package:")
    }


def kill_server() -> str:
    return run(["kill-server"], timeout=15)


def start_server() -> str:
    return run(["start-server"], timeout=20)
