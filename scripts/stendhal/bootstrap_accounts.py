#!/usr/bin/env python3
"""Create or verify the local QA account pool through the original protocol."""
import argparse
import os
import re

from gameqa.accounts import observer_pool, target_pool
from gameqa.bridge import Bridge, BridgeError
from gameqa.config import load_config, resolve_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    game = config["games"]["stendhal"]
    # 账号池：UI 角色（target）+ API 目标池 + 观察者池，都按角色共用同一个密码环境变量
    accounts = {game["target"]: game["player_password_env"]}
    accounts.update({name: game["player_password_env"] for name in target_pool(game)})
    accounts.update({name: game["observer_password_env"] for name in observer_pool(game)})
    for username, env in accounts.items():
        if not re.fullmatch(r"qa(?:player|observer)[a-z]*", username):
            raise ValueError("bootstrap only creates reserved local QA accounts")
        password = os.environ[env]
        bridge = Bridge([os.path.expandvars(s) for s in game["bridge_command"]],
                        cwd=resolve_path(config, game.get("bridge_cwd", ".")),
                        timeout=game.get("timeout", 30))
        try:
            bridge.call("connect", {"host": game["host"], "port": game["port"]})
            try:
                bridge.call("create_account", {"username": username, "password": password})
            except BridgeError as error:
                # Stendhal validates character collisions before checking the account table.
                if not any(code in str(error) for code in ("FAILED_PLAYER_EXISTS", "FAILED_CHARACTER_EXISTS")):
                    raise
            account = bridge.call("login", {"username": username, "password": password})
            if username not in account["characters"]:
                bridge.call("create_character", {"character": username})
            state = bridge.call("choose_character", {"character": username})
            if state.get("name") != username:
                raise ValueError("selected character differs from requested QA account")
            print(f"Verified local account and character: {username}")
        finally:
            bridge.close()


if __name__ == "__main__":
    main()
