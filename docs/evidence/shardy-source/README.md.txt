<a href="./README.md">![Static Badge](https://img.shields.io/badge/english-118027)</a>
<a href="./README.ru.md">![Static Badge](https://img.shields.io/badge/russian-0390fc)</a>
<p align="center">
    <picture>
        <source media="(prefers-color-scheme: dark)" srcset="media/logo-ttt-dark.png">
        <source media="(prefers-color-scheme: light)" srcset="media/logo-ttt.png">
        <img alt="Tic-Tac-Toe game on Shardy" height="256" width="256" src="media/logo-ttt.png">
    </picture>
</p>
<h3 align="center">Tic-Tac-Toe game on Shardy</h3>
<h4 align="center">Framework for online games and apps</h4>
<p align="center">
    <a href="https://github.com/mopsicus/shardy">Shardy</a> · <a href="https://github.com/mopsicus/shardy-template">Template</a> · <a href="https://github.com/mopsicus/shardy-unity">Unity client</a> · <a href="https://github.com/mopsicus/shardy-tictactoe/issues">Report Bug</a>
</p>

# 💬 Overview

This is a simplest game server for Tic-Tac-Toe (T3) game made on Shardy. Popupal game in multiplayer implementation on TypeScript and Node.js.

Shardy is framework for online games and applications on Node.js. It provides the basic functionality for building microservices solutions: mobile, social, web, multiplayer games, realtime applications, chats, middleware services, etc.
 
[Read about Shardy](https://github.com/mopsicus/shardy) 💪

# ✨ Features

- Start/stop search free games
- Matchmaking
- Send player's turn
- Send `leave` to opponent
- Detect draw and game over
- Save current game score

# 🚀 Quick start

It's really easy to run your own T3 backend for testing:

1. Clone it
    ```
    git clone git@github.com:mopsicus/shardy-tictactoe.git
    ```
2. Install Shardy and all dependencies:
    ```
    npm install
    ```
3. Edit `.env.dev`
4. Run debug mode
    ```
    npm run debug
    ```

## Here's something you won't find in this repo

- Reconnect to game
- Save results to DB
- Foolproofing
- `Right` files structure and code organization

> [!IMPORTANT]
> This is a simplest game server for T3, don't expect full backend functionality, it's just a demo :)

See the [template](https://github.com/mopsicus/shardy-template) for example how to start develop your own backend or service and [documentation](https://github.com/mopsicus/shardy) for all API methods and examples.

## Client for Tic-Tac-Toe

To connect and play on this demo game server use sample from the [Unity client](https://github.com/mopsicus/shardy-unity) repo. The Unity client allows you to create apps for Android, iOS, and WebGL for Shardy services.

# 🤝 Support

You can support Shardy by using any of the ways below:

* Bitcoin (BTC): bc1qaejavqm0r2fnx3d6mhvt8r6uqzwzun5vwkryn2
* USDT (TRC20): TLDPntuWNZRZTiWmtaKvZH7cVFXuf5TQvS
* TON: UQBrv16QN-6y2Jba0IgoKJEGB4u7_0ilPw8BXDH7M9NnExhw
* Visa, Mastercard via [Boosty](https://boosty.to/mopsicus/donate)
* MIR via [CloudTips](https://pay.cloudtips.ru/p/9f507669)

# ✉️ Contact

Before you ask a question, it is best to search for existing [issues](https://github.com/mopsicus/shardy-tictactoe/issues) that might help you. Anyway, you can ask any questions and send suggestions by [email](mailto:mail@mopsicus.ru) or [Telegram](https://t.me/mopsicus).

# 🔑 License

Tic-Tac-Toe for Shardy is licensed under the [MIT License](./LICENSE). Use it for free and be happy. 🎉
