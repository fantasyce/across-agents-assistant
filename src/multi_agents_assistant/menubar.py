from __future__ import annotations


from AppKit import NSApplication, NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
from Foundation import NSObject

_menubar_controller = None

import objc

from .app import MultiAgentsAssistantApp

class MenuBarController(NSObject):
    def initWithApp_(self, app: MultiAgentsAssistantApp):
        self = objc.super(MenuBarController, self).init()
        if self is None:
            return self

        self._app = app

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        
        # Keep a strong reference to prevent disappearing
        self._status_item_strong_ref = self._status_item
        self._status_item.retain() # Explicitly retain in Objective-C
        
        import os
        import sys
        from AppKit import NSImage, NSSize

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        icon_path = os.path.join(base_path, "assets", "menubar_icon.png")
        if os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if image:
                image.setTemplate_(False) # Set to False to keep the original colors
                image.setSize_(NSSize(22, 22))
                self._status_item.button().setImage_(image)
                # Keep the title empty when using image
                self._status_item.button().setTitle_("")
        else:
            self._status_item.button().setTitle_("小落")

        self._menu = NSMenu.alloc().init()

        self._status_line = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("状态: 初始化", None, "")
        self._menu.addItem_(self._status_line)
        self._menu.addItem_(NSMenuItem.separatorItem())

        self._toggle_realtime_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "实时对话: 关闭", "toggleRealtime:", ""
        )
        self._toggle_realtime_item.setTarget_(self)
        self._menu.addItem_(self._toggle_realtime_item)

        self._menu.addItem_(NSMenuItem.separatorItem())
        
        # Add Agent Settings button
        self._settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("⚙️ 配置智能体大脑...", "openAgentSettings:", "")
        self._settings_item.setTarget_(self)
        self._menu.addItem_(self._settings_item)
        self._menu.addItem_(NSMenuItem.separatorItem())

        self._quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quit:", "q")
        self._quit_item.setTarget_(self)
        self._menu.addItem_(self._quit_item)

        self._status_item.setMenu_(self._menu)

        self._refresh_ui()

        # Update UI repeatedly
        from PyObjCTools import AppHelper
        AppHelper.callLater(1.0, self.tick)

        return self

    def tick(self):
        self._refresh_ui()
        from PyObjCTools import AppHelper
        AppHelper.callLater(1.0, self.tick)

    def _refresh_ui(self):
        realtime = self._app.is_realtime_enabled()
        self._toggle_realtime_item.setTitle_(f"实时对话: {'开启' if realtime else '关闭'}")
        self._status_line.setTitle_(f"状态: {self._app.get_status_text()}")

    def toggleRealtime_(self, _):
        self._app.set_realtime_enabled(not self._app.is_realtime_enabled())
        self._refresh_ui()
        
    def openAgentSettings_(self, _):
        import threading
        import subprocess
        import sys
        import os
        
        # Reload manager when UI closes so app uses new active agent
        def run_ui():
            if getattr(sys, 'frozen', False):
                subprocess.run([sys.executable, "ui"])
            else:
                main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
                subprocess.run([sys.executable, main_py, "ui"])
            
            # Force app's openclaw client to reload agent config
            self._app._agent_manager.config = self._app._agent_manager._load_config()
            self._app._openclaw.initialized = False
            self._app._openclaw.initialize()
            
        threading.Thread(target=run_ui, daemon=True).start()

    def quit_(self, _):
        import logging
        logger = logging.getLogger("multi_agents_assistant")
        logger.info("👋 用户点击了退出菜单，准备结束进程...")
        
        # Perform graceful shutdown of all threads, models and streams
        self._app.shutdown()
        
        # Finally terminate the NSApplication loop
        NSApplication.sharedApplication().terminate_(None)

def run_menubar(app: MultiAgentsAssistantApp):
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular
    from PyObjCTools import AppHelper
    
    app_instance = NSApplication.sharedApplication()
    app_instance.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    
    controller = MenuBarController.alloc().initWithApp_(app)
    
    global _persistent_controller
    _persistent_controller = controller
    
    app.start_background()
    
    app_instance.activateIgnoringOtherApps_(True)
    AppHelper.runEventLoop()
