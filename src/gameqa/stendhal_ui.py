import os
from pathlib import Path
import time


ASSETS = Path(__file__).resolve().parents[2] / "assets" / "stendhal"
MAP_REGION = (96, 203, 565, 555)


def map_touch(position, size, destination):
    """Project original 32px tiles through the clamped 640x480 camera."""
    # ponytail: fixed 720x1280 baseline; remeasure canvas if browser geometry changes.
    x, y = position
    width, height = size
    tx, ty = destination
    if not (0 <= x < width and 0 <= y < height and -.5 <= tx < width - .5 and -.5 <= ty < height - .5):
        raise ValueError('map coordinates outside zone')
    offsets = (max(0, min(x * 32 + 16 - 320, width * 32 - 640)),
               max(0, min(y * 32 + 16 - 240, height * 32 - 480)))
    left, top, right, bottom = MAP_REGION
    relative = (tx * 32 + 16 - offsets[0], ty * 32 + 16 - offsets[1])
    if not (0 <= relative[0] < 640 and 0 <= relative[1] < 480):
        raise ValueError('destination is outside visible canvas; use a nearer waypoint')
    return (round(left + relative[0] * (right - left) / 640),
            round(top + relative[1] * (bottom - top) / 480))


def minimap_touch(size, destination):
    """Original minimap sends moveto directly, bypassing NPC/item default actions."""
    # ponytail: these four maps fit the unpanned 128px minimap; remeasure for >64 tiles.
    width, height = size
    x, y = destination
    if not (0 < width <= 64 and 0 < height <= 64 and 0 <= x < width and 0 <= y < height):
        raise ValueError('destination requires an unpanned minimap tile')
    scale = max(2, min(128 / height, 128 / width))
    def pixel(tile, origin):
        nearest = round(origin + (tile + .5) * scale * 720 / 980)
        # Empirical native MouseEvent offsets include Chrome's subpixel border layout.
        for candidate in (nearest, nearest - 1, nearest + 1):
            if int(int((candidate - origin) * 980 / 720 + .5) / scale) == tile:
                return candidate
        raise ValueError('minimap tile has no safe physical pixel')
    # Twenty real clicks froze this 720x1280 calibration; see the projection self-check.
    return (pixel(x, .5), pixel(y, 202.55))


class StendhalUI:
    # Fixed emulator resolution is part of this project's baseline.
    # Fields use offsets from a detected button, not coordinates of moving NPCs.
    def __init__(self, android, config):
        self.android, self.config = android, config
        self.entered = False
        self.travel_log_open = False
        self.timing = {}
        # 只测不改：把公开方法包一层计时，跑完写进证据，用来回答"UI 用例的时间花在哪"。
        for name in ("ensure_login", "say", "dialogue", "walk", "check_image", "check_image_absent",
                     "open_travel_log", "close_travel_log", "relogin", "move_item", "choose_item_menu",
                     "open_creature_menu", "choose_creature_menu", "close"):
            setattr(self, name, self._timed(name, getattr(self, name)))

    def _timed(self, name, function):
        def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                return function(*args, **kwargs)
            finally:
                row = self.timing.setdefault(name, [0, 0.0])
                row[0] += 1
                row[1] += time.monotonic() - start
        return wrapper

    def record_timing(self):
        """把 UI 层耗时与截图数量写进证据（每个 UI 用例结束时调用，成功失败都写）。"""
        rows = [{"operation": name, "count": count, "total_seconds": round(total, 2),
                 "average_seconds": round(total / count, 3)}
                for name, (count, total) in sorted(self.timing.items(), key=lambda kv: -kv[1][1])]
        shots = self.android.timing.get("screenshot", [0, 0.0])
        self.android.evidence.data["diagnostics"]["ui_timing"] = {
            "operations": rows,
            "screenshots": shots[0],
            "screenshot_seconds": round(shots[1], 2),
            "device_operations": self.android.timing_summary(),
        }
        return rows

    def wait_for_image(self, path, title, seconds=75, threshold=0.7):
        """轮询等界面渲染出来，命中后照常记一条观察；轮询本身不写记录。

        为什么需要：`am start` 到首帧之间，硬件渲染约 5 秒，软件渲染（swiftshader）要 30–60 秒。
        以前只 sleep(5) 就找模板，第 2 轮常常还没渲染完 → 登录步骤误报失败。
        """
        from airtest.core.api import Template, exists

        template = Template(str(path), threshold=threshold)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if exists(template):
                break
            time.sleep(2)
        return self.android.locate_image(path, title)

    def ensure_login(self):
        self.entered = False
        self.travel_log_open = False
        # A disconnected page still displays the game canvas. Start a fresh UI session.
        self.android.device.adb.shell(["am", "force-stop", "com.android.chrome"])
        # A distinct URL avoids reusing the disconnected page's client state.
        separator = '&' if '?' in self.config['url'] else '?'
        url = self.config['url'] + separator + 'qa_session=' + str(time.time_ns())
        self.android.device.adb.shell(["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", url,
                                       "--es", "com.android.browser.application_id", "gameqa.stendhal"])
        button = self.wait_for_image(ASSETS / "login.png", "登录按钮")
        # ADBTOUCH uses a native tap at its default duration; longer duration is a swipe.
        # Activate the form, then focus the empty field, before sending text once.
        username = (button[0] + 150, button[1] - 36)
        self.android.touch(username, "激活登录表单")
        self.android.touch(username, "聚焦用户名输入框")
        time.sleep(0.5)
        self.android.locate_image(ASSETS / 'username-focused.png', '输入前确认用户名框实际聚焦',
                                  region=(170, 255, 352, 285), threshold=0.9)
        self.android.text(self.config["target"], "输入测试用户名", enter=False)
        self.android.locate_image(ASSETS / 'username-qaplayer.png', '登录前确认用户名已实际输入',
                                  region=(175, 255, 347, 283), threshold=0.9)
        self.android.touch((button[0] + 150, button[1] - 18), "密码输入框")
        time.sleep(0.5)
        password = os.environ[self.config["player_password_env"]]
        self.android.text(password, "输入本地测试密码", enter=False)
        self.android.hide_keyboard()
        self.android.touch_image(ASSETS / "login.png", "提交登录")
        time.sleep(1)
        self.android.touch_image(ASSETS / "character-qaplayer.png", "选择测试角色")
        time.sleep(2)
        self.android.locate_image(ASSETS / "send.png", "进入游戏后聊天按钮")
        self.entered = True
        self.android.screenshot("角色进入实际游戏地图")

    def say(self, words):
        button = self.android.locate_image(ASSETS / "send.png", "聊天发送按钮")
        self.android.touch((button[0] - 200, button[1]), "聚焦游戏聊天框")
        self.android.text(words, f"在游戏界面提交对话：{words}", enter=True)
        time.sleep(0.3)
        self.android.hide_keyboard()
        time.sleep(0.6)
        self.android.screenshot(f"提交后的游戏画面：{words}")

    def dialogue(self, *words):
        for word in words:
            self.say(word)

    def walk(self, observer, zone, size, destination, *, next_zone=None):
        before = observer.inspect()
        attrs = before['attributes']
        self.android.evidence.check('点击行走前处于预期地图', attrs['zoneid'], zone,
                                    '原版semos.xml地图连接；只读坐标决定屏内投影')
        origin = (int(attrs['x']), int(attrs['y']))
        # Ground border clicks add extend; the original minimap has no extend.
        border = any(value != int(value) for value in destination)
        touch = map_touch(origin, size, destination) if border else minimap_touch(size, destination)
        self.android.evidence.data['diagnostics'].setdefault('ui_route', []).append(
            {'zone': zone, 'size': size, 'origin': origin, 'destination': destination,
             'touch': touch, 'next_zone': next_zone,
             'method': 'actual ground border tap' if border else 'actual original minimap tap; no GM movement'})
        self.android.touch(touch, f'实际地图点击行走：{zone} → {destination}')
        def arrived(state):
            a = state['attributes']
            return a['zoneid'] == next_zone if next_zone else (
                a['zoneid'] == zone and (int(a['x']), int(a['y'])) == destination and float(a.get('speed', 0)) == 0)
        after = observer.await_state(arrived, '等待实际地图行走或门户切换', timeout=35)
        self.android.evidence.check('实际行走到达目标地图或坐标', arrived(after), True,
                                    '原版MiniMapComponent.onClick直接moveto；边界用Ground.extend；原版门户')
        time.sleep(0.6)  # Let client tile interpolation finish before projecting the next tap.
        self.android.screenshot('实际行走到达后的地图画面')
        return after

    def check_image_absent(self, name, title, region, source):
        from airtest.core.api import Template
        x1, y1, x2, y2 = region
        screen = self.android.device.snapshot()
        match = Template(str(ASSETS / (name + '.png')), threshold=.9).match_in(screen[y1:y2, x1:x2])
        self.android.evidence.check(title, bool(match), False, source + '; 固定任务日志正文区域图像反例')
        self.android.screenshot(title)

    def open_travel_log(self, completed=False):
        self.say('/progressstatus')
        self.travel_log_open = True
        self.android.locate_image(ASSETS / 'travel-log-title.png', 'Travel Log窗口标题')
        if completed:
            self.android.touch_image(ASSETS / 'travel-log-completed-tab.png', '切换Completed Quests')
        time.sleep(0.8)
        self.android.screenshot('完成任务日志' if completed else '进行中任务日志')

    def close_travel_log(self):
        self.android.touch_image(ASSETS / 'travel-log-close.png', '关闭Travel Log窗口')
        self.travel_log_open = False

    def check_image(self, name, title, region, source, *, threshold=0.9):
        position = self.android.locate_image(ASSETS / (name + '.png'), title,
                                             region=region, threshold=threshold)
        self.android.evidence.check(title, bool(position), True, source + '; 固定区域Airtest图像断言')
        self.android.screenshot(title)

    def relogin(self, observer):
        # The local static client has no /account/logout.html website deployment.
        # Check actual disconnection/persistence; do not claim HTTP account logout.
        self.close()
        observer.await_presence(False)
        self.ensure_login()
        observer.await_presence(True)

    def close(self):
        # Release the original NPC's conversation before disconnecting the player.
        try:
            if self.entered:
                if self.travel_log_open:
                    self.close_travel_log()
                self.say("bye")
        finally:
            self.android.device.adb.shell(["am", "force-stop", "com.android.chrome"])
            self.entered = False

    def open_creature_menu(self, label, region, *, offset=30, threshold=0.9):
        """长按地图上生物的标签，打开它的 Action 菜单。

        标签随身体移动，所以用**真实屏幕位置**（图像定位的结果）而不是 GM 坐标；
        标签与身体之间那点像素偏移收在这里，用例层只说"打开哪个生物"。
        """
        position = self.android.locate_image(ASSETS / (label + '.png'), '定位地图中真实生物标签',
                                             region=region, threshold=threshold)
        self.android.screenshot('静止生物实际画面')
        self.android.touch((position[0], position[1] + offset), '长按实际生物身体打开Action菜单',
                           duration=0.5)
        time.sleep(0.4)

    def choose_creature_menu(self, entry, region, *, threshold=0.85):
        """点 Action 菜单项。

        阈值比一般断言低：菜单文字随屏幕位置有亚像素差异，这个数是原用例记录反例后定下的。
        """
        button = self.android.locate_image(ASSETS / (entry + '-menu.png'),
                                           '确认原版菜单：' + entry, region=region, threshold=threshold)
        self.android.touch(button, '选择一次原版菜单：' + entry)
        time.sleep(0.4)

    def choose_item_menu(self, icon, region, menu):
        position = self.android.locate_image(ASSETS / (icon + '.png'), '定位道具：' + icon,
                                             region=region, threshold=0.9)
        self.android.touch(position, '长按道具打开菜单：' + icon, duration=0.5)
        time.sleep(0.4)
        button = self.android.locate_image(ASSETS / (menu + '-menu.png'), '道具菜单：' + menu,
                                           region=(530, 220, 665, 570), threshold=0.9)
        self.android.touch(button, '选择道具菜单：' + menu)
        time.sleep(0.4)

    def move_item(self, icon, origin, destination, region, *, menu="hold"):
        # Original mobile client supports Hold, then touching an inventory slot.
        self.choose_item_menu(icon, origin, menu)
        target = self.android.locate_image(ASSETS / (destination + '.png'), '目标槽位：' + destination,
                                           region=region, threshold=0.9)
        self.android.touch(target, '将道具放入：' + destination)
        time.sleep(0.6)
