import webview
import os

try:
    import AppKit
except ImportError:
    pass

import os
html_path = os.path.join(os.path.dirname(__file__), "assets", "web", "index.html")
with open(html_path, "r", encoding="utf-8") as f:
    HTML_CONTENT = f.read()

from .agent_ids import LOCAL_AGENT_ID, normalize_agent_id


def check_mic_permission() -> bool:
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
        import threading

        mic_status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)

        if mic_status != 3: # 3 is AVAuthorizationStatusAuthorized
            event = threading.Event()
            granted_result = [False]
            def handler(granted):
                granted_result[0] = granted
                event.set()
            AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, handler)
            event.wait()

            if granted_result[0]:
                # PortAudio caches devices on load. If permission was just granted,
                # we MUST restart the process for it to detect the microphone.
                import subprocess
                import sys
                import os
                import logging
                logging.getLogger("across_agents_assistant").info("Microphone permission granted. Restarting to apply...")
                subprocess.Popen([sys.executable] + sys.argv[1:])
                os._exit(0)

            return granted_result[0]
        return True
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"Permission check failed: {e}")
        return True

class MainApi:
    def __init__(self, app, window):
        self.app = app
        self.window = window
        self.manager = app._agent_manager
        self.is_maximized = False

    def get_config(self):
        from .icons import AGENT_ICONS
        conf = self.manager.config.copy()
        conf["icons"] = AGENT_ICONS
        return conf

    def get_ui_state(self):
        return {
            "voice_on": self.app._voice_mode_enabled.is_set(),
            "continuous_on": self.app._continuous_mode.is_set(),
            "silent_on": self.app._silent_mode.is_set()
        }

    def set_active(self, agent_id):
        self.manager.set_active_agent(normalize_agent_id(agent_id) or agent_id)
        # Hot reload local
        self.app._local_agent.initialized = False
        self.app._local_agent.initialize()
        return True

    def detect_or_config(self, agent_id):
        import subprocess
        import shutil
        normalized_agent_id = normalize_agent_id(agent_id) or agent_id
        from .local_agent_health import LOCAL_AGENT_SPECS

        executable_name = str(
            (LOCAL_AGENT_SPECS.get(normalized_agent_id) or {}).get("executable")
            or ("openclaw" if normalized_agent_id == LOCAL_AGENT_ID else normalized_agent_id)
        )
        path = shutil.which(executable_name)
        if not path:
            try:
                result = subprocess.run(
                    ["/bin/zsh", "-l", "-c", "npm config get prefix"],
                    capture_output=True, text=True
                )
                npm_prefix = result.stdout.strip()
                if npm_prefix:
                    potential_path = os.path.join(npm_prefix, "bin", executable_name)
                    if os.path.exists(potential_path) and os.access(potential_path, os.X_OK):
                        path = potential_path
                if not path:
                    result = subprocess.run(["/bin/zsh", "-l", "-c", f"which {executable_name}"], capture_output=True, text=True)
                    output = result.stdout.strip()
                    if output and "not found" not in output.lower() and os.path.exists(output):
                        path = output
            except Exception:
                pass
        if not path:
            common_paths = [
                os.path.expanduser(f"~/.local/bin/{executable_name}"),
                os.path.expanduser(f"~/.cargo/bin/{executable_name}"),
                f"/opt/homebrew/bin/{executable_name}",
                f"/usr/local/bin/{executable_name}",
                f"/usr/bin/{executable_name}",
                f"/bin/{executable_name}",
            ]
            for cp in common_paths:
                if os.path.exists(cp) and os.access(cp, os.X_OK):
                    path = cp
                    break
        if path and os.path.exists(path):
            config = self.manager.get_agent_config(agent_id)
            config["executable_path"] = path
            self.manager.update_agent(agent_id, config)
            return {"success": True, "msg": f"成功检测到 {agent_id}！"}
        return {"success": False, "msg": f"未检测到 {agent_id}，请前往设置配置"}

    def trigger_single_turn(self):
        import os
        os.system("afplay /System/Library/Sounds/Glass.aiff &")
        self.app._manual_listen.set()
        return True
    def send_structured_message(self, structured_content, target_agent=None):
        # Stop any ongoing TTS and interrupt listening to process text
        self.app._hotkey_interrupt.set()

        import threading
        threading.Thread(target=self.app._handle_user_structured_text, args=(structured_content, target_agent), daemon=True).start()

    def send_text_message(self, text, target_agent=None):
        # Stop any ongoing TTS and interrupt listening to process text
        self.app._hotkey_interrupt.set()

        # Dispatch manually instead of queue to pass the specific target agent
        import threading
        threading.Thread(target=self.app._handle_user_text, args=(text, target_agent), daemon=True).start()

    def open_settings_window(self):
        # Open the settings UI in a new process or window
        import subprocess
        import sys
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "ui"])
        else:
            import os
            main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
            subprocess.Popen([sys.executable, main_py, "ui"])

    def close_window(self):
        self.window.destroy()

    def minimize_window(self):
        self.window.minimize()

    def maximize_window(self):
        import sys
        if sys.platform == 'darwin':
            try:
                import AppKit
                from PyObjCTools import AppHelper
                import webview.platforms.cocoa as cocoa

                i = cocoa.BrowserView.instances.get(self.window.uid)
                if i and i.window:
                    # Native zoom toggles between maximize and restore automatically
                    AppHelper.callAfter(i.window.zoom_, None)
                    return
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Native zoom failed: {e}")

        # Fallback for non-macOS or if native fails
        try:
            if self.is_maximized:
                self.window.restore()
                self.is_maximized = False
            else:
                self.window.maximize()
                self.is_maximized = True
        except:
            pass

    def toggle_silent_mode(self):
        if self.app._silent_mode.is_set():
            self.app._silent_mode.clear()
            return False
        else:
            self.app._silent_mode.set()
            # Stop ongoing TTS if switching to silent (but don't interrupt the conversation loop)
            self.app._tts_interrupt.set()
            return True

    def toggle_continuous(self):
        import os
        if self.app._continuous_mode.is_set():
            self.app._continuous_mode.clear()
            self.app._voice_mode_enabled.clear()
            self.app._hotkey_interrupt.set()
            os.system("afplay /System/Library/Sounds/Funk.aiff &")
            return False
        else:
            if not check_mic_permission():
                return False
            self.app._hotkey_interrupt.clear()
            self.app._continuous_mode.set()
            self.app._voice_mode_enabled.set()
            self.app.ensure_speechcli_running()
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
            return True

    def list_directory(self, path=None, show_hidden=False):
        import os
        import logging
        logger = logging.getLogger("across_agents_assistant")
        if not path or path == "" or path == "~":
            path = os.path.expanduser("~")
        else:
            path = os.path.expanduser(path)

        logger.info(f"list_directory called for path: {path}, show_hidden: {show_hidden}")
        try:
            entries = []
            for entry in os.scandir(path):
                # Skip hidden files if not show_hidden
                if not show_hidden and entry.name.startswith('.'):
                    continue

                is_dir = entry.is_dir()
                entries.append({
                    "name": entry.name,
                    "is_dir": is_dir,
                    "absolute_path": entry.path
                })

            # Sort: directories first, then alphabetically
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            logger.info(f"list_directory success: {len(entries)} items")
            return {"success": True, "entries": entries}
        except Exception as e:
            logger.error(f"list_directory error: {e}")
            return {"success": False, "error": str(e)}

    def reveal_in_finder(self, path):
        import subprocess
        try:
            subprocess.run(['open', '-R', path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def rename_file(self, old_path, new_name):
        import os
        try:
            dir_name = os.path.dirname(old_path)
            new_path = os.path.join(dir_name, new_name)
            os.rename(old_path, new_path)
            return {"success": True, "new_path": new_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_file(self, path):
        import os
        import shutil
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

_tray_globals = {}

class MacTrayManager:
    pass

try:
    import AppKit
    import objc
    class MacTrayManager(AppKit.NSObject):
        def setupTray_(self, window):
            try:
                app = AppKit.NSApplication.sharedApplication()
                statusbar = AppKit.NSStatusBar.systemStatusBar()
                statusitem = statusbar.statusItemWithLength_(-1)

                # Try loading the generated menubar icon first
                import os, sys
                if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                    base_path = sys._MEIPASS
                else:
                    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

                icon_path = os.path.join(base_path, "assets", "menubar_icon.png")
                if os.path.exists(icon_path):
                    img = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
                    if img:
                        img.setTemplate_(True) # Automatically invert colors for dark/light mode
                        img.setSize_(AppKit.NSSize(18, 18))
                        statusitem.button().setImage_(img)
                else:
                    # Fallback to system symbol
                    img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("sparkles", None)
                    if img:
                        img.setTemplate_(True) # Adapts to light/dark mode
                        statusitem.button().setImage_(img)
                    else:
                        statusitem.button().setTitle_("AAA")

                menu = AppKit.NSMenu.alloc().init()

                class MenuHandler(AppKit.NSObject):
                    def showWindow_(self, sender):
                        window.show()
                        AppKit.NSApp.activateIgnoringOtherApps_(True)

                    def toggleContinuous_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            import os
                            if app_inst._continuous_mode.is_set():
                                app_inst._continuous_mode.clear()
                                app_inst._voice_mode_enabled.clear()
                                app_inst._hotkey_interrupt.set()
                                sender.setTitle_("开启持续对话")
                                os.system("afplay /System/Library/Sounds/Funk.aiff &")
                                app_inst._logger.info("🔴 用户通过菜单栏关闭了持续对话")
                                if app_inst.on_message_callback:
                                    app_inst.on_message_callback("system", "Continuous_Off", None)
                            else:
                                app_inst._continuous_mode.set()
                                app_inst._voice_mode_enabled.set()
                                app_inst.ensure_speechcli_running()
                                sender.setTitle_("关闭持续对话")
                                os.system("afplay /System/Library/Sounds/Glass.aiff &")
                                app_inst._logger.info("🟢 用户通过菜单栏开启了持续对话")
                                if app_inst.on_message_callback:
                                    app_inst.on_message_callback("system", "Continuous_On", None)

                    def toggleSilent_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            if app_inst._silent_mode.is_set():
                                app_inst._silent_mode.clear()
                                sender.setTitle_("开启静音模式")
                            else:
                                app_inst._silent_mode.set()
                                sender.setTitle_("关闭静音模式")
                                app_inst._hotkey_interrupt.set()

                    def quitApp_(self, sender):
                        app_inst = getattr(window, 'voice_app', None)
                        if app_inst:
                            app_inst.is_quitting = True
                        window.destroy()
                        import os
                        os._exit(0)

                handler = MenuHandler.alloc().init()

                item_show = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打开对话窗口", "showWindow:", "")
                item_show.setTarget_(handler)
                menu.addItem_(item_show)

                menu.addItem_(AppKit.NSMenuItem.separatorItem())

                # We need to set the initial title based on app state
                voice_title = "关闭语音输入"
                initial_title = "切换为单次对话"
                silent_title = "开启静音模式"
                app_inst = getattr(window, 'voice_app', None)
                if app_inst:
                    if not app_inst._voice_mode_enabled.is_set():
                        voice_title = "开启语音输入"
                    if not app_inst._continuous_mode.is_set():
                        initial_title = "切换为连续对话"
                    if app_inst._silent_mode.is_set():
                        silent_title = "关闭静音模式"

                item_voice = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(voice_title, "toggleVoice:", "")
                item_voice.setTarget_(handler)
                menu.addItem_(item_voice)

                item_toggle = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(initial_title, "toggleContinuous:", "")
                item_toggle.setTarget_(handler)
                menu.addItem_(item_toggle)

                item_silent = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(silent_title, "toggleSilent:", "")
                item_silent.setTarget_(handler)
                menu.addItem_(item_silent)

                menu.addItem_(AppKit.NSMenuItem.separatorItem())

                item_quit = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出小落", "quitApp:", "")
                item_quit.setTarget_(handler)
                menu.addItem_(item_quit)

                statusitem.setMenu_(menu)

                # Prevent GC
                _tray_globals['statusitem'] = statusitem
                _tray_globals['handler'] = handler
                _tray_globals['menu'] = menu

                # Hijack Cmd+Q from the main menu
                mainMenu = app.mainMenu()
                if mainMenu:
                    appMenu = mainMenu.itemAtIndex_(0).submenu()
                    if appMenu:
                        for i in range(appMenu.numberOfItems()):
                            item = appMenu.itemAtIndex_(i)
                            # Override the default "Quit" action with our custom handler
                            if item.keyEquivalent() == "q":
                                item.setTarget_(handler)
                                item.setAction_(objc.selector(handler.quitApp_, signature=b'v@:@'))
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to setup tray: {e}")
except ImportError:
    pass

def create_tray(window):
    try:
        import objc
        manager = MacTrayManager.alloc().init()
        # MUST run on main thread, otherwise AppKit UI creation will fail silently or crash
        manager.performSelectorOnMainThread_withObject_waitUntilDone_(objc.selector(manager.setupTray_, signature=b'v@:@'), window, False)

        # Keep manager alive just in case
        _tray_globals['manager'] = manager
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"Failed to initialize tray: {e}")

def start_main_ui(app):
    window = webview.create_window('', html=HTML_CONTENT, width=1200, height=800, text_select=True, frameless=True, transparent=True, easy_drag=False)
    window.voice_app = app  # Attach to window for tray access
    api = MainApi(app, window)
    window.expose(api.get_config, api.get_ui_state, api.set_active, api.detect_or_config, api.send_text_message, api.send_structured_message, api.open_settings_window, api.close_window, api.minimize_window, api.maximize_window, api.toggle_silent_mode, api.toggle_continuous, api.trigger_single_turn, api.list_directory, api.reveal_in_finder, api.rename_file, api.delete_file)

    def on_closing():
        if getattr(app, 'is_quitting', False):
            return True
        window.hide()
        return False
    window.events.closing += on_closing

    # Hook app callbacks to UI
    def on_message(role, text, target_agent=None):
        # Use evaluate_js to update UI
        escaped_text = text.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
        try:
            if target_agent:
                window.evaluate_js(f"addMessage('{role}', '{escaped_text}', '{target_agent}')")
            else:
                window.evaluate_js(f"addMessage('{role}', '{escaped_text}', null)")
        except Exception as e:
            import logging
            logging.getLogger("across_agents_assistant").error(f"UI update failed: {e}")

    app.on_message_callback = on_message

    # Poll for config changes to update sidebar
    import time
    def poll_config():
        last_agent = api.manager.get_active_agent()
        while True:
            time.sleep(1)
            current_agent = api.manager.get_active_agent()
            if current_agent != last_agent:
                last_agent = current_agent
                try:
                    window.evaluate_js("loadData()")
                except Exception:
                    pass
    import threading
    threading.Thread(target=poll_config, daemon=True).start()

    webview.start(create_tray, window, debug=False)
