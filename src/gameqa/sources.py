"""规则出处索引：用例层只引用这里的名字，不写字面 URL。

出处固定到官方源码 commit；升级游戏版本时必须整份同步，不允许在用例里另写 URL。
行号区间属于断言细节，允许在用例里写成 `常量 + "#Lx-Ly"`。
"""

COMMIT = "cbe0825e9b46f2a8adf9adce8c5747ece13b17a0"
SOURCE = f"https://github.com/arianne/stendhal/blob/{COMMIT}/"

# 商店与价格
SHOP_TRADE_REPLIES = SOURCE + "src/games/stendhal/server/entity/npc/behaviour/impl/SellerBehaviour.java#L112-L116 (Congratulations! Here is/are your ...); BuyerBehaviour.java#L83 (Thanks! Here is your money.)"
SELL_ITEMS_PRICES = SOURCE + "data/conf/shops/sell_items.xml#L6-L16 (Margaret: cheese=20, beer=10)"
SELL_TO_KEEPER_PRICES = SOURCE + "data/conf/shops/buy_items.xml#L6-L13 (Siandra: cheese=5)"
SELL_ITEMS_APPLE = SOURCE + "data/conf/shops/sell_items.xml#L6-L16 (apple=10, cheese=20)"
SELLER_ADDER = SOURCE + "src/games/stendhal/server/entity/npc/behaviour/adder/SellerAdder.java"
SELLER_BEHAVIOUR = SOURCE + "src/games/stendhal/server/entity/npc/behaviour/impl/SellerBehaviour.java"
SELLER_TRANSACT = SOURCE + "src/games/stendhal/server/entity/npc/behaviour/impl/SellerBehaviour.java#L101-L125"
NORMAL_PRICE = SOURCE + "src/games/stendhal/server/entity/player/Player.java#L2407-L2409"

# 数量解析
PARSER_EXPRESSION = SOURCE + "src/games/stendhal/common/parser/Expression.java#L85-L97"
PARSER_SENTENCE = SOURCE + "src/games/stendhal/common/parser/SentenceImplementation.java#L151-L158"
PREFIX_MANAGER = SOURCE + "src/games/stendhal/common/grammar/PrefixManager.java#L64"

# 背包、容器与物品
STORAGE = SOURCE + "src/games/stendhal/server/entity/RPEntity.java#L1961-L2103"
PLAYER_BAG_SLOT = SOURCE + "src/games/stendhal/server/entity/slot/PlayerBagSlot.java#L24-L40"
PLAYER_TRADE_SLOT = SOURCE + "src/games/stendhal/server/entity/slot/PlayerTradeSlot.java#L35-L47"
SHEEP_SELLER = SOURCE + "src/games/stendhal/server/maps/semos/village/SheepSellerNPC.java#L36 (BUYING_PRICE=30); #L70-L90 (一次多只/已有羊分别拒绝)"
SHEEP_PET = SOURCE + "src/games/stendhal/server/entity/player/Player.java#L1150-L1190 (hasSheep/hasPet/getSheep/getPet)"
FORSAKE = SOURCE + "src/games/stendhal/server/actions/pet/ForsakeAction.java (forsake: 放走羊/宠)"
FOOD_ITEMS = SOURCE + "data/conf/items/food.xml#L1518-L1538"
BUCKLER_ITEM = SOURCE + "data/conf/items/shields.xml#L48-L71"

# NPC 与任务
BARMAID_NPC = SOURCE + "src/games/stendhal/server/maps/semos/tavern/BarMaidNPC.java#L54-L61"
BEER_QUEST_REWARD = SOURCE + ("src/games/stendhal/server/maps/quests/BeerForHayunn.java"
                              " (20 gold, 50 XP, 10 karma, nonrepeatable)")
BEER_QUEST_FLOW = SOURCE + "src/games/stendhal/server/maps/quests/BeerForHayunn.java#L77-L97"
QUEST_OFFER = SOURCE + "src/games/stendhal/server/entity/npc/quest/QuestOfferBuilder.java#L194-L259"
QUEST_COMPLETE = SOURCE + "src/games/stendhal/server/entity/npc/quest/SimpleQuestCompleteBuilder.java#L89-L139"
BRING_ITEM_TASK = SOURCE + "src/games/stendhal/server/entity/npc/quest/BringItemTask.java"

# 等级与成长
LEVEL_RULES = SOURCE + "src/games/stendhal/common/Level.java#L38-L43"
LEVEL_UPDATE = SOURCE + "src/games/stendhal/server/entity/RPEntity.java#L1162-L1175"

# 第二游戏 Shardy（仓库 commit 与 Stendhal 无关，单独一套基址）
SHARDY_COMMIT = "ed8e978917cbe5aba79009928e8c3b92a34b81cc"
SHARDY_SOURCE = f"https://github.com/mopsicus/shardy-tictactoe/blob/{SHARDY_COMMIT}/src/"
SHARDY_GAME = SHARDY_SOURCE + "Game.ts"
SHARDY_ROUND = SHARDY_GAME + "#L105-L127"
SHARDY_TURN = SHARDY_GAME + "#L137-L154"
SHARDY_WIN = SHARDY_GAME + "#L188-L192"
SHARDY_STATE_SYNC = SHARDY_GAME + "#L119-L126;L148-L150"
SHARDY_SCORE = SHARDY_GAME + "#L85-L89"
SHARDY_TURN_ORDER = SHARDY_GAME + "#L83"
SHARDY_T3_BROADCAST = SHARDY_SOURCE + "T3Service.ts#L176-L195"
SHARDY_RULES_DOC = "docs/Shardy规则.md：3×3棋盘；同一玩家三子连成行、列或任一对角线获胜；无胜者且九格全满才和局"
