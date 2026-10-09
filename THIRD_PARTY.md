# 来源与许可

本项目原创代码采用 GPL-2.0-or-later（正文见 LICENSE）。上游文件保留各自原许可与版权声明。

| 组件 | 固定来源 | 上游许可 / 本项目用途 |
|---|---|---|
| Stendhal 服务端 / Java客户端 | arianne/stendhal v1.49，cbe0825e9b46f2a8adf9adce8c5747ece13b17a0 | GPL-2.0-or-later；本地被测游戏与官方协议依赖 |
| Stendhal 网页客户端与 ItemMap 补丁 | 同一 commit，src/js | AGPL-3.0-or-later；补丁文件保留版权声明 |
| Marauroa | 官方发行包内 3.9.8 | 许可见下载包 libs/LICENSES.txt；协议桥复用官方实现 |
| Stendhal 图片 / 地图 / 声音 | 官方客户端发行包 | 多种许可，保留上游包与源码内说明；未把整套资产改称本项目原创 |
| Shardy 后端 | mopsicus/shardy-tictactoe，ed8e978917cbe5aba79009928e8c3b92a34b81cc | MIT；许可副本 adapters/shardy_bridge/UPSTREAM-LICENSE |
| Shardy 展示界面 | 本项目 integrations/shardy_client | 本项目客户端，非上游 Unity 客户端；仅显示真实服务端广播 |
| Airtest / pytest | requirements-lock.txt | 安装依赖，未复制其源代码进本项目 |

第三方二进制、游戏源码仓库、数据库和账号密码留在本地 work 目录，公开源码通过准备脚本从固定来源重建。assets/stendhal 下的定位图片来自实际游戏截图，仅用于此版本与分辨率的界面定位。
