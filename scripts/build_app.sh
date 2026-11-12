#!/bin/bash
# 构建可分发的自包含 macOS App：内嵌 Python 运行时 + 精简 Qt + 源码。
# 产物写入 dist/，可用 VERSION / PYROOT 覆盖默认值。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${VERSION:-0.2.0}"
ARCH="$(uname -m)"
NAME="ScrcpyStudio-${VERSION}-macOS-${ARCH}"
PYROOT="${PYROOT:-$(awk -F' = ' '/^home /{print $2}' "$ROOT/.venv/pyvenv.cfg" | sed 's|/bin$||')}"
PYVER="$(awk -F' = ' '/^version /{print $2}' "$ROOT/.venv/pyvenv.cfg" | cut -d. -f1,2)"
OUT="$ROOT/dist"
WORK="$(mktemp -d -t scrcpy-build)"
APP="$WORK/ScrcpyStudio.app"
RES="$APP/Contents/Resources"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$APP/Contents/MacOS" "$RES" "$OUT"

echo "==> [1/6] 应用壳与 Info.plist"
cp "$ROOT/ScrcpyStudio.app/Contents/Info.plist" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP/Contents/Info.plist"
cat > "$APP/Contents/MacOS/ScrcpyStudio" <<'LAUNCH'
#!/bin/bash
# 自包含启动：全部依赖都在 Contents/Resources 内，不依赖系统 Python
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
export DYLD_LIBRARY_PATH="$RES/runtime/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
export PYTHONHOME="$RES/runtime"
export PYTHONPATH="$RES/site-packages:$RES/app"
exec "$RES/runtime/bin/python3.13" "$RES/app/app.py" "$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/ScrcpyStudio"

echo "==> [2/6] 应用源码"
mkdir -p "$RES/app"
for item in app.py core ui README.md requirements.txt; do
    cp -R "$ROOT/$item" "$RES/app/"
done
find "$RES/app" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$RES/app" -name "*.pyc" -delete

echo "==> [3/6] 内嵌 Python $PYVER 运行时 ($PYROOT)"
mkdir -p "$RES/runtime/bin" "$RES/runtime/lib/python$PYVER"
cp "$PYROOT/bin/python3.13" "$RES/runtime/bin/python3.13"
cp "$PYROOT/lib/libpython3.13.dylib" "$RES/runtime/lib/libpython3.13.dylib"
# 只取标准库：源解释器自带的 site-packages / 测试 / GUI 工具全部排除
# （lib-dynload 必须保留，内含 zlib / _socket 等标准扩展）
tar -cf - \
    --exclude='site-packages' --exclude='test' --exclude='idlelib' \
    --exclude='tkinter' --exclude='ensurepip' --exclude='__pycache__' \
    --exclude='*.pyc' -C "$PYROOT/lib/python$PYVER" . \
    | tar -xf - -C "$RES/runtime/lib/python$PYVER"

echo "==> [4/6] 精简第三方依赖"
SP_SRC="$(echo "$ROOT"/.venv/lib/python*/site-packages)"
SP="$RES/site-packages"
mkdir -p "$SP"
# 按白名单复制，跳过 pip / setuptools / 缓存（运行时不需要）
tar -cf - \
    --exclude='pip' --exclude='pip-*' --exclude='setuptools' \
    --exclude='setuptools-*' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='*.pyi' -C "$SP_SRC" . \
    | tar -xf - -C "$SP"
PS="$SP/PySide6"

rm -rf "$SP/pip" "$SP"/pip-* "$SP/setuptools" "$SP"/setuptools-* \
       "$SP"/*.dist-info/RECORD.jws
find "$SP" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$SP" -name "*.pyc" -delete
find "$SP" -name "*.pyi" -delete

# PySide6 自带的开发工具 / QML / 翻译文件，Widgets 程序完全用不到
rm -rf "$PS/Designer.app" "$PS/Linguist.app" "$PS/Assistant.app" \
       "$PS/Qt/qml" "$PS/Qt/translations" "$PS/Qt/mkspecs" \
       "$PS/Qt/phrasebooks" "$PS/Qt/libexec" "$PS/Qt/include" \
       "$PS/include" "$PS/examples" "$PS/scripts" \
       "$PS/qmlls" "$PS/qmlformat" "$PS/qmlformat" "$PS/lrelease" \
       "$PS/lupdate" "$PS/rcc" "$PS/uic" "$PS/assistant" \
       "$PS/designer" "$PS/linguist" "$PS/pyside6-rcc" \
       "$PS/pyside6-uic" "$PS/pyside6-designer" "$PS/pyside6-lrelease" \
       "$PS/pyside6-lupdate" "$PS/pyside6-qmlls" "$PS/pyside6-qmlformat" 2>/dev/null || true

# 只保留 Widgets 程序需要的 Qt framework
KEEP_FW="QtCore QtGui QtWidgets QtDBus QtNetwork QtSvg QtXml QtConcurrent"
for fw in "$PS/Qt/lib"/*.framework; do
    [ -e "$fw" ] || continue
    base="$(basename "$fw" .framework)"
    case " $KEEP_FW " in *" $base "*) ;; *) rm -rf "$fw" ;; esac
done

# 只保留 QtCore / QtGui / QtWidgets 三个 Python 绑定模块
for so in "$PS"/*.abi3.so; do
    [ -e "$so" ] || continue
    base="$(basename "$so")"; mod="${base%%.*}"
    case "$mod" in QtCore|QtGui|QtWidgets) ;; *) rm -f "$so" ;; esac
done

# Qt 插件：平台 / 图片格式 / 样式 / TLS，其余（QML、SQL、Designer 等）删掉
KEEP_PLUGINS="platforms imageformats styles iconengines tls"
for d in "$PS/Qt/plugins"/*; do
    [ -e "$d" ] || continue
    base="$(basename "$d")"
    case " $KEEP_PLUGINS " in *" $base "*) ;; *) rm -rf "$d" ;; esac
done

echo "     精简后 Resources: $(du -sh "$RES" | cut -f1)"

echo "==> [5/6] 签名并验证可启动"
codesign --force --deep -s - "$APP" 2>&1 | tail -3 || true
# 验证时把 HOME 指到临时目录，避免 MainWindow.persist 写到真实用户配置
FAKEHOME="$WORK/fakehome"
mkdir -p "$FAKEHOME"
APP_PATH="$APP" FAKEHOME="$FAKEHOME" "$PYROOT/bin/python3.13" - <<'PY'
import os, subprocess, sys, time
app = os.environ["APP_PATH"]
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=os.environ["FAKEHOME"])
p = subprocess.Popen([app + "/Contents/MacOS/ScrcpyStudio"], env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(4)
alive = p.poll() is None
p.terminate()
try:
    out, _ = p.communicate(timeout=5)
except subprocess.TimeoutExpired:
    p.kill(); out, _ = p.communicate()
print("    App 启动 4 秒后仍存活:", alive)
if out.strip():
    print("    输出:", out.strip()[:600])
sys.exit(0 if alive and "Traceback" not in out else 1)
PY

echo "==> [6/6] 打包"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/$NAME.app.zip"
(cd "$OUT" && shasum -a 256 "$NAME.app.zip" > "$NAME.app.zip.sha256")
# 顺带产出一份纯源码快照，方便开发者从源码安装
tar -czf "$OUT/$NAME-source.tar.gz" \
    --exclude='.git' --exclude='.venv' --exclude='dist' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
    --exclude='crop-*.png' --exclude='config.json' -C "$ROOT" .
(cd "$OUT" && shasum -a 256 "$NAME-source.tar.gz" > "$NAME-source.tar.gz.sha256")

echo
echo "构建完成："
ls -lh "$OUT/$NAME.app.zip" "$OUT/$NAME-source.tar.gz"
cat "$OUT/$NAME.app.zip.sha256"
