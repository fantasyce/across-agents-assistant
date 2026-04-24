#!/bin/bash

# Exit on any error
set -e

PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
APP_NAME="AcrossAgentsAssistant"
BUILD_DIR="$PROJECT_ROOT/build"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
DMG_DIR="$BUILD_DIR/dmg"

echo "=== 1. Cleaning up previous builds ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo "=== 2. Building Python Backend ==="
cd "$PROJECT_ROOT/backend"
# Use the correct python environment
PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN="./.venv/bin/python"
fi

# We assume pyinstaller is installed. If not, this will fail.
PYTHONPATH=src $PYTHON_BIN -m PyInstaller --name "backend" --onefile --clean --noconfirm \
    main.py

echo "=== 3. Building macOS Client (Release) ==="
cd "$PROJECT_ROOT/macOS-Client"
swift build -c release --disable-sandbox

echo "=== 4. Creating App Bundle Structure ==="
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

echo "=== 5. Copying Executables and Resources ==="
# Copy Swift executable
cp "$PROJECT_ROOT/macOS-Client/.build/release/AcrossAgentsAssistantClient" "$APP_DIR/Contents/MacOS/$APP_NAME"

# Copy Backend executable
cp "$PROJECT_ROOT/backend/dist/backend" "$APP_DIR/Contents/Resources/backend"

# Copy Assets bundle if it exists
if [ -d "$PROJECT_ROOT/macOS-Client/.build/release/AcrossAgentsAssistant_AcrossAgentsAssistantClient.bundle" ]; then
    cp -R "$PROJECT_ROOT/macOS-Client/.build/release/AcrossAgentsAssistant_AcrossAgentsAssistantClient.bundle" "$APP_DIR/Contents/Resources/"
fi

echo "=== 6. Generating Info.plist ==="
cat <<PLIST > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.fantasyce.$APP_NAME</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSScreenCaptureUsageDescription</key>
    <string>AcrossAgentsAssistant 需要截屏权限以获取屏幕内容，从而允许 AI 理解您的当前屏幕信息。</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>AcrossAgentsAssistant 需要麦克风权限以支持语音对话。</string>
    <key>NSSystemExtensionUsageDescription</key>
    <string>AcrossAgentsAssistant 需要访问系统扩展。</string>
</dict>
</plist>
PLIST

echo "=== 6.5 Signing App ==="
codesign --force --deep --sign - --entitlements "$PROJECT_ROOT/macOS-Client/Entitlements.entitlements" "$APP_DIR"

echo "=== 7. Creating DMG ==="
mkdir -p "$DMG_DIR"
cp -R "$APP_DIR" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

echo "Attempting to create DMG (this may fail in some sandboxed environments)..."
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_DIR" -ov -format UDZO "$BUILD_DIR/$APP_NAME.dmg" || echo "DMG creation skipped/failed due to environment restrictions. You can find the .app bundle at $APP_DIR"

echo "=== Done! App is ready at $APP_DIR ==="
