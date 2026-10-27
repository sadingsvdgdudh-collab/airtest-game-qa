"""Airtest controls for the project's client of the original Shardy server."""
from pathlib import Path
import time

from .bridge import TransientError


ASSETS = Path(__file__).resolve().parents[2] / "assets" / "shardy"


class ShardyUI:
    def __init__(self, android, config):
        self.android, self.config = android, config
        self.anchor = None

    def wait_image(self, name, title, timeout=90):
        """等页面出现再动手：Chrome 冷启动在模拟器上常常超过 5 秒，固定 sleep 会截到白屏。"""
        from .bridge import TransientError
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.android.locate_image(ASSETS / name, title)
            except TransientError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)

    def start(self):
        self.android.device.adb.shell(["am", "force-stop", "com.android.chrome"])
        self.android.device.adb.shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", self.config["url"]])
        anchor = self.wait_image("connect.png", "连接原版Shardy服务端")
        self.android.touch(anchor, "连接原版Shardy服务端")
        self.anchor = self.wait_image("start.png", "连接成功后的开始匹配按钮")
        self.android.touch(self.anchor, "界面开始真实匹配")

    def position(self, x, y):
        if x not in range(3) or y not in range(3) or self.anchor is None:
            raise ValueError("invalid board cell or client not started")
        # Supported baseline: Android14, 720x1280, Chrome normal zoom.
        return self.anchor[0] + (x - 1) * 172, self.anchor[1] + (-489, -317, -145)[y]

    def turn(self, x, y):
        self.android.touch(self.position(x, y), f"界面实际落子({x},{y})")

    def check_piece(self, x, y, player):
        from airtest.core.api import Template
        import numpy as np
        from PIL import Image
        template = Template(str(ASSETS / ("x.png" if player == 0 else "o.png")), threshold=0.8)
        center = self.position(x, y)

        def read():
            path = self.android.screenshot(f"读取格子({x},{y})实际图像")
            with Image.open(path) as screenshot:
                region = screenshot.crop((center[0] - 72, center[1] - 72, center[0] + 72, center[1] + 72))
                matched = template.match_in(np.asarray(region)[:, :, ::-1].copy())
            if matched is None:
                raise TransientError(f"expected piece image absent at cell ({x},{y}), player={player}")
            return True

        visible = self.android.evidence.observe(f"视觉识别格子({x},{y})的{'X' if player == 0 else 'O'}", read)
        self.android.evidence.check("客户端在指定格显示原服确认的棋子", visible, True,
                                    "docs/Shardy规则.md；integrations/shardy_client/index.html render()")
