from pathlib import Path
import logging
import time

from .bridge import TransientError


class AndroidDevice:
    """设备层；顺带把每个动作的耗时累计下来，供 UI 用例的成本分析（不改行为）。"""

    def __init__(self, uri, evidence):
        from airtest.core.api import connect_device
        # Airtest DEBUG includes literal input commands; don't log typed credentials.
        logging.getLogger("airtest").setLevel(logging.WARNING)
        self.device = connect_device(uri)
        self.evidence = evidence
        self.timing = {}          # 操作名 → [次数, 累计秒数]

    def timed(self, name, function, *args, **kwargs):
        start = time.monotonic()
        try:
            return function(*args, **kwargs)
        finally:
            row = self.timing.setdefault(name, [0, 0.0])
            row[0] += 1
            row[1] += time.monotonic() - start

    def timing_summary(self):
        """按时长降序，给出「操作 / 次数 / 总秒 / 平均秒」；UI 用例跑完写进证据。"""
        return [{"operation": name, "count": count, "total_seconds": round(total, 2),
                 "average_seconds": round(total / count, 3)}
                for name, (count, total) in sorted(self.timing.items(), key=lambda kv: -kv[1][1])]

    def screenshot(self, label):
        from airtest.core.api import snapshot
        name = f"screen-{len(self.evidence.data['attachments']) + 1:02d}.png"
        path = self.evidence.folder / name
        start = time.monotonic()
        try:
            snapshot(filename=str(path), msg=label)
            self.evidence.attach(path, label)
        finally:
            row = self.timing.setdefault("screenshot", [0, 0.0])
            row[0] += 1
            row[1] += time.monotonic() - start
        return path

    def locate_image(self, path, title, *, region=None, threshold=0.7):
        from airtest.core.api import Template, exists
        def locate():
            template = Template(str(Path(path)), threshold=threshold)
            if region is None:
                target = exists(template)
            else:
                x1, y1, x2, y2 = region
                screen = self.device.snapshot()
                target = template.match_in(screen[y1:y2, x1:x2])
                if target:
                    target = (target[0] + x1, target[1] + y1)
            self.evidence.data['diagnostics'].setdefault('visual_observations', []).append(
                {'title': title, 'template': Path(path).name, 'region': region,
                 'threshold': threshold, 'matched': bool(target), 'position': target or None})
            if not target:
                self.screenshot(f"{title}：定位失败")
                raise TransientError(f"image not found: {path}")
            return target
        return self.evidence.observe(f"定位：{title}", locate)

    def touch_image(self, path, title):
        from airtest.core.api import touch
        position = self.locate_image(path, title)
        self.evidence.action(title, lambda: touch(position))
        self.screenshot(title)

    def touch(self, position, title, *, duration=0.01):
        from airtest.core.api import touch
        self.evidence.action(title, lambda: touch(position, duration=duration))
        self.screenshot(title)

    def text(self, content, title, enter=True):
        from airtest.core.api import text
        self.evidence.action(title, lambda: text(content, enter=enter))

    def key(self, key, title):
        from airtest.core.api import keyevent
        self.evidence.action(title, lambda: keyevent(key))

    def hide_keyboard(self):
        if self.device.adb.is_keyboard_shown():
            self.key("BACK", "收起已显示的键盘")
