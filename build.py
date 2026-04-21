import PyInstaller.__main__
import os
import subprocess
import plistlib

PyInstaller.__main__.run([
    'main.py',
    '--name=AcrossAgentsAssistant',
    '--windowed',  # Prevent console window appearing
    '--noconfirm', # Overwrite existing output
    '--clean',
    '--add-data=src/across_agents_assistant/icons.py:across_agents_assistant',
    '--add-data=models/whisper-small:models/whisper-small',
    '--add-data=assets:assets',
    '--copy-metadata=faster_whisper',
    '--collect-data=faster_whisper',
    '--collect-all=webview',
    '--collect-all=torchcodec',
    '--collect-all=torchaudio',
    '--collect-all=soundfile',
    '--hidden-import=pynput.keyboard._darwin',
    '--hidden-import=pynput.mouse._darwin',
    '--hidden-import=ctranslate2',
    '--hidden-import=faster_whisper',
    '--hidden-import=sounddevice',
    '--hidden-import=webrtcvad',
    '--hidden-import=AVFoundation',
    '--hidden-import=ApplicationServices',
    '--paths=src',
    '--icon=assets/app_icon.icns',
])

plist_path = 'dist/AcrossAgentsAssistant.app/Contents/Info.plist'
if os.path.exists(plist_path):
    with open(plist_path, 'rb') as f:
        plist = plistlib.load(f)
    
    # Critical: Add descriptions for privacy prompts, otherwise macOS silently drops requests
    plist['NSMicrophoneUsageDescription'] = '助手需要使用麦克风来接收你的语音指令。'
    plist['NSAppleEventsUsageDescription'] = '助手需要辅助功能权限来监听全局快捷键。'
    
    # Change Application menu name (next to Apple Logo)
    plist['CFBundleName'] = 'Across-Agents Assistant'
    plist['CFBundleDisplayName'] = 'Across-Agents Assistant'
    
    with open(plist_path, 'wb') as f:
        plistlib.dump(plist, f)
        
    print("Patched Info.plist. Re-signing app...")
    # Add entitlements for microphone access and library validation
    entitlements = 'entitlements.plist'
    with open(entitlements, 'w') as f:
        f.write('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
</dict>
</plist>''')
    # Use deep signing and runtime options with library validation disabled
    subprocess.run(['codesign', '--force', '--deep', '--options', 'runtime', '--entitlements', entitlements, '--sign', '-', 'dist/AcrossAgentsAssistant.app'], check=True)
    os.remove(entitlements)
    print("Re-sign complete.")
