package games.stendhal.server.script;

import java.nio.charset.StandardCharsets;
import java.util.*;
import games.stendhal.common.Direction;
import games.stendhal.common.Level;
import games.stendhal.server.core.engine.SingletonRepository;
import games.stendhal.server.core.scripting.ScriptImpl;
import games.stendhal.server.entity.creature.DomesticAnimal;
import games.stendhal.server.entity.item.Item;
import games.stendhal.server.entity.item.StackableItem;
import games.stendhal.server.entity.npc.SpeakerNPC;
import games.stendhal.server.core.pathfinder.Node;
import games.stendhal.server.entity.player.Player;
import games.stendhal.server.entity.slot.Slots;
import marauroa.common.game.RPObject;
import marauroa.common.game.RPSlot;
import org.json.simple.JSONValue;
import org.json.simple.parser.JSONParser;

/** Test-server-only observer and fixture helper. Business actions never use this script. */
public final class QaProbe extends ScriptImpl {
    private static final Map<String, Saved> SNAPSHOTS = new HashMap<>();
    private static final List<String> KEYED = List.of("!kills", "!tutorial", "!visited", "skills");
    private static final List<String> COMMERCE = List.of("npc_purchases", "npc_sales", "looted_items");
    private static final List<String> COUNTERS = List.of("looted", "produced", "obtained", "mined", "sown", "harvested", "bought", "sold");
    private static final List<String> RESTORABLE = List.of("bag", "equipment", "quests", "xp", "hp", "level", "base_hp", "karma", "location", "features", "npc_purchases", "npc_sales", "looted_items", "item_counter_cache", "atk_xp", "def_xp", "atk", "def", "!kills", "!tutorial", "!visited", "skills");
    private static final Set<String> ALLOWED = Set.of("request_id", "op", "target", "timeout_ms", "money", "items", "quests", "xp", "hp", "karma", "zone", "x", "y", "near_npc", "snapshot_id", "older_than_seconds", "forget_token", "features");
    private static final class Saved {
        final String target, zone;
        final int x, y, xp, hp, level, baseHp, atkXp, defXp, atk, def;
        final double karma;
        final List<Map<String, String>> bag = new ArrayList<>();
        final Map<String, List<Map<String, String>>> equipment = new LinkedHashMap<>();
        final Map<String, Map<String, String>> keyed = new LinkedHashMap<>();
        final Map<String, Map<String, Integer>> counters;
        final Map<String, String> quests;
        final Map<String, String> features = new LinkedHashMap<>();
        final Map<String, Map<String, String>> commerce = new LinkedHashMap<>();
        final Map<String, Object> before;
        final long createdAt = System.currentTimeMillis();
        Saved(Player player) {
            target = player.getName(); zone = player.getZone().getID().getID();
            x = player.getX(); y = player.getY(); xp = player.getXP(); hp = player.getHP();
            level = player.getLevel(); baseHp = player.getBaseHP(); karma = player.getKarma();
            atkXp = player.getAtkXP(); defXp = player.getDefXP(); atk = player.getAtk(); def = player.getDef();
            quests = quests(player); counters = counters(player); before = inspect(player);
            if (player.hasMap("features")) features.putAll(player.getMap("features"));
            for (RPObject item : player.getSlot("bag")) {
                if (!item.slots().isEmpty()) throw new IllegalArgumentException("Nested inventory is not supported by this fixture helper");
                bag.add(attributes(item));
            }
            for (String key : COMMERCE) commerce.put(key, player.hasMap(key) ? new LinkedHashMap<>(player.getMap(key)) : new LinkedHashMap<>());
            for (String slot : Slots.EQUIPMENT.getNames()) {
                List<Map<String, String>> items = new ArrayList<>();
                for (RPObject item : player.getSlot(slot)) {
                    if (!item.slots().isEmpty()) throw new IllegalArgumentException("Nested equipment is not supported by this fixture helper");
                    items.add(attributes(item));
                }
                equipment.put(slot, items);
            }
            for (String slot : KEYED) keyed.put(slot, keyed(player, slot));
        }
    }
    private static Map<String, Object> obj(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) result.put((String) values[i], values[i + 1]);
        return result;
    }
    private static Map<String, String> attributes(RPObject object) {
        Map<String, String> result = new LinkedHashMap<>();
        for (String key : object) result.put(key, object.get(key));
        return result;
    }
    private static Map<String, Object> tree(RPObject object) {
        Map<String, Object> slots = new LinkedHashMap<>();
        for (RPSlot slot : object.slots()) {
            List<Object> items = new ArrayList<>();
            for (RPObject item : slot) items.add(tree(item));
            slots.put(slot.getName(), items);
        }
        return obj("name", object.has("name") ? object.get("name") : null, "attributes", attributes(object), "slots", slots);
    }
    private static Map<String, String> quests(Player player) {
        Map<String, String> result = new LinkedHashMap<>();
        for (String name : player.getQuests()) result.put(name, player.getQuest(name));
        return result;
    }
    private static Map<String, Object> inspect(Player player) {
        Map<String, Object> result = tree(player);
        List<Object> inventory = new ArrayList<>();
        for (RPSlot slot : player.slots()) for (RPObject object : slot) if (object instanceof Item) {
            Item item = (Item) object;
            inventory.add(obj("slot", slot.getName(), "name", item.getName(), "quantity", item.getQuantity()));
        }
        result.put("inventory", inventory); result.put("quests", quests(player));
        result.put("features", player.hasMap("features") ? new LinkedHashMap<>(player.getMap("features")) : new LinkedHashMap<>());
        result.put("trade_state", player.getTradeState().name());
        result.put("bag_full", player.getSlot("bag").isFull());
        List<Object> ground = new ArrayList<>();
        for (RPObject object : player.getZone()) if (object instanceof Item) ground.add(tree(object));
        result.put("ground_items", ground);
            result.put("pet", pet(player));
        result.put("money", player.getNumberOfEquipped("money"));
        result.put("xp", player.getXP()); result.put("hp", player.getHP());
        result.put("level", player.getLevel()); result.put("base_hp", player.getBaseHP()); result.put("karma", player.getKarma());
        List<String> statuses = new ArrayList<>();
        player.getStatusList().getStatuses().forEach(status -> statuses.add(status.getName()));
        result.put("statuses", statuses);
        Map<String, Object> commerce = new LinkedHashMap<>();
        for (String key : COMMERCE) commerce.put(key, player.hasMap(key) ? new LinkedHashMap<>(player.getMap(key)) : new LinkedHashMap<>());
        result.put("commerce", commerce);
        result.put("item_counter_cache", counters(player));
        result.put("atk_xp", player.getAtkXP()); result.put("def_xp", player.getDefXP());
        result.put("atk", player.getAtk()); result.put("def", player.getDef());
        Map<String, Object> keyed = new LinkedHashMap<>();
        for (String slot : KEYED) keyed.put(slot, keyed(player, slot));
        result.put("keyed", keyed);
        return result;
    }
    private static Map<String, String> keyed(Player player, String slot) {
        Map<String, String> result = new LinkedHashMap<>();
        if (player.hasSlot(slot)) for (RPObject object : player.getSlot(slot)) result.putAll(attributes(object));
        result.remove("id"); result.remove("zoneid");
        return result;
    }
    private static Map<String, Integer> counter(Player player, String name) {
        // Test-only reflection: public Player APIs expose no cache reset. Preserve all
        // eight original maps instead of rebuilding through the 1.49 constructor,
        // which mistakenly loads sold.* entries into bought.
        try {
            java.lang.reflect.Field owner = Player.class.getDeclaredField("itemCounter");
            owner.setAccessible(true);
            Object handler = owner.get(player);
            java.lang.reflect.Field field = handler.getClass().getDeclaredField(name);
            field.setAccessible(true);
            return (Map<String, Integer>) field.get(handler);
        } catch (ReflectiveOperationException error) { throw new IllegalStateException("Could not access test player item counter cache", error); }
    }
    private static Map<String, Map<String, Integer>> counters(Player player) {
        Map<String, Map<String, Integer>> result = new LinkedHashMap<>();
        for (String name : COUNTERS) result.put(name, new LinkedHashMap<>(counter(player, name)));
        return result;
    }
    private static int number(Map<?, ?> args, String key) {
        Object value = args.get(key);
        if (!(value instanceof Number) || ((Number) value).doubleValue() != ((Number) value).intValue()) throw new IllegalArgumentException(key + " must be an integer");
        int result = ((Number) value).intValue();
        if (result < 0 || result > 1000000) throw new IllegalArgumentException(key + " must be between 0 and 1000000");
        return result;
    }
    private static Item makeItem(String name, int count) {
        Item item = SingletonRepository.getEntityManager().getItem(name);
        if (item == null) throw new IllegalArgumentException("Unknown item: " + name);
        if (!item.canBeEquippedIn("bag")) throw new IllegalArgumentException("Item cannot be stored in bag: " + name);
        if (item instanceof StackableItem) ((StackableItem) item).setQuantity(count);
        else if (count != 1) throw new IllegalArgumentException("Non-stackable item quantity must be 1: " + name);
        return item;
    }
    private static void removeBag(Player player) {
        RPSlot slot = player.getSlot("bag");
        List<RPObject> contents = new ArrayList<>();
        for (RPObject item : slot) contents.add(item);
        for (RPObject item : contents) slot.remove(item.getID());
    }
    private static void restoreItems(Player player, String slot, List<Map<String, String>> items) {
        List<RPObject> current = new ArrayList<>();
        for (RPObject item : player.getSlot(slot)) current.add(item);
        for (RPObject item : current) player.getSlot(slot).remove(item.getID());
        for (Map<String, String> fields : items) {
            Item item = makeItem(fields.get("name"), fields.containsKey("quantity") ? Integer.parseInt(fields.get("quantity")) : 1);
            for (Map.Entry<String, String> field : fields.entrySet()) if (!field.getKey().equals("id") && !field.getKey().equals("zoneid")) item.put(field.getKey(), field.getValue());
            if (!player.equip(slot, item)) throw new IllegalStateException("Could not restore " + slot + " item " + item.getName());
        }
    }
    private static Map<String, Object> restore(Player player, Player admin, Saved saved) {
        player.stopAttack(); player.clearPath(); player.stop();
        // Clear every touched item slot before putting the saved objects back.
        removeBag(player);
        for (String slot : saved.equipment.keySet()) restoreItems(player, slot, Collections.emptyList());
        restoreItems(player, "bag", saved.bag);
        for (Map.Entry<String, List<Map<String, String>>> entry : saved.equipment.entrySet()) restoreItems(player, entry.getKey(), entry.getValue());
        player.updateItemAtkDef();
        for (String name : new ArrayList<>(player.getQuests())) player.removeQuest(name);
        for (Map.Entry<String, String> quest : saved.quests.entrySet()) player.setQuest(quest.getKey(), quest.getValue());
        if (player.hasMap("features")) for (String name : new ArrayList<>(player.getMap("features").keySet())) player.unsetFeature(name);
        for (Map.Entry<String, String> feature : saved.features.entrySet()) player.setFeature(feature.getKey(), feature.getValue());
        player.setXP(saved.xp); player.setLevel(saved.level); player.setBaseHP(saved.baseHp); player.setHP(saved.hp);
        player.setAtkXP(saved.atkXp); player.setDefXP(saved.defXp); player.setAtk(saved.atk); player.setDef(saved.def);
        player.addKarma(saved.karma - player.getKarma());
        for (Map.Entry<String, Map<String, String>> entry : saved.commerce.entrySet()) {
            // Marauroa 3.9.8 removeMap only marks deletion; getMap returns a copy.
            // Restore entries through the supported key API and normalize absent maps as empty.
            if (player.hasMap(entry.getKey())) for (String key : player.getMap(entry.getKey()).keySet()) player.remove(entry.getKey(), key);
            for (Map.Entry<String, String> value : entry.getValue().entrySet()) player.put(entry.getKey(), value.getKey(), value.getValue());
        }
        for (String name : COUNTERS) { counter(player, name).clear(); counter(player, name).putAll(saved.counters.get(name)); }
        if (!player.getZone().getID().getID().equals(saved.zone) || player.getX() != saved.x || player.getY() != saved.y) {
            if (!player.teleport(saved.zone, saved.x, saved.y, Direction.DOWN, admin)) throw new IllegalStateException("Could not restore location");
        }
        // Teleport may add tutorial/visited keys, so restore keyed data afterwards.
        for (Map.Entry<String, Map<String, String>> entry : saved.keyed.entrySet()) {
            for (String key : keyed(player, entry.getKey()).keySet()) player.setKeyedSlot(entry.getKey(), key, null);
            for (Map.Entry<String, String> value : entry.getValue().entrySet()) player.setKeyedSlot(entry.getKey(), value.getKey(), value.getValue());
        }
        player.notifyWorldAboutChanges();
        boolean adjusted = player.getX() != saved.x || player.getY() != saved.y;
        int distance = Math.abs(player.getX() - saved.x) + Math.abs(player.getY() - saved.y);
        if (!player.getZone().getID().getID().equals(saved.zone) || (adjusted && (distance > 1 || !player.getZone().collides(player, saved.x, saved.y)))) throw new IllegalStateException("Location restoration is outside the permitted adjacent-tile policy");
        return obj("location_adjusted", adjusted, "requested", obj("zone", saved.zone, "x", saved.x, "y", saved.y), "actual", obj("zone", player.getZone().getID().getID(), "x", player.getX(), "y", player.getY()), "max_manhattan_distance", 1, "reason", adjusted ? "Original tile is occupied or blocked" : "Exact original position restored");
    }
    /**
     * 宠物/家畜的只读视图。羊与宠是两套（Sheep/Pet 都继承 DomesticAnimal，各自持有 private hunger），
     * 饥饿没有公开的数值读取接口，所以给出玩家 LOOK 时看到的那段 describe() 文本。
     */
    private static Map<String, Object> pet(Player player) {
        DomesticAnimal animal = player.hasSheep() ? player.getSheep() : player.getPet();
        Map<String, Object> view = obj("has_sheep", player.hasSheep(), "has_pet", player.hasPet());
        if (animal == null) {
            view.put("animal", null);
            return view;
        }
        view.put("animal", obj(
                "type", animal.getClass().getSimpleName(),
                "name", animal.getName(),
                "owner", animal.getOwner() == null ? null : animal.getOwner().getName(),
                "weight", animal.getWeight(),
                "hp", animal.getHP(),
                "zone", animal.getZone() == null ? null : animal.getZone().getID().getID(),
                "x", animal.getX(), "y", animal.getY(),
                "description", animal.describe()));
        return view;
    }

    private static Map<String, Object> projection(Map<String, Object> state) {
        Map<?, ?> attrs = (Map<?, ?>) state.get("attributes");
        Map<String, Object> carrying = new TreeMap<>();
        List<String> slots = new ArrayList<>(Slots.EQUIPMENT.getNames()); slots.add("bag");
        for (String slot : slots) {
        Map<String, Object> items = new TreeMap<>();
        for (Object raw : (List<?>) ((Map<?, ?>) state.get("slots")).get(slot)) {
            Map<String, String> fields = new TreeMap<>((Map<String, String>) ((Map<?, ?>) raw).get("attributes"));
            fields.remove("id"); fields.remove("zoneid");
            String key = fields.get("name") + ":" + JSONValue.toJSONString(fields);
            items.put(key, ((Number) items.getOrDefault(key, 0)).intValue() + 1);
        }
        carrying.put(slot, items);
        }
        return obj("items", carrying, "quests", state.get("quests"), "xp", state.get("xp"), "hp", state.get("hp"), "level", state.get("level"), "base_hp", state.get("base_hp"), "karma", state.get("karma"), "commerce", state.get("commerce"), "item_counter_cache", state.get("item_counter_cache"), "atk_xp", state.get("atk_xp"), "def_xp", state.get("def_xp"), "atk", state.get("atk"), "def", state.get("def"), "keyed", state.get("keyed"), "zone", attrs.get("zoneid"), "x", attrs.get("x"), "y", attrs.get("y"));
    }
    private static Object prepare(Player player, Player admin, Map<?, ?> args) {
        for (Saved snapshot : SNAPSHOTS.values()) if (snapshot.target.equals(player.getName())) throw new IllegalStateException("An active snapshot already exists for this target; restore it first");
        Map<String, Integer> amounts = new LinkedHashMap<>();
        if (args.containsKey("items")) {
            for (Map.Entry<?, ?> item : ((Map<?, ?>) args.get("items")).entrySet()) {
                String name = (String) item.getKey();
                amounts.put(name, number(Collections.singletonMap(name, item.getValue()), name));
            }
        }
        if (args.containsKey("money")) amounts.put("money", number(args, "money"));
        for (Map.Entry<String, Integer> amount : amounts.entrySet()) {
            if (amount.getValue() > 0) makeItem(amount.getKey(), amount.getValue());
            for (Item item : player.getAllEquipped(amount.getKey())) if (!item.getContainerSlot().getName().equals("bag")) throw new IllegalArgumentException("Fixture item exists outside bag: " + amount.getKey());
        }
        if (args.containsKey("xp")) number(args, "xp");
        if (args.containsKey("hp")) number(args, "hp");
        if (args.containsKey("karma") && (!(args.get("karma") instanceof Number) || !Double.isFinite(((Number) args.get("karma")).doubleValue()))) throw new IllegalArgumentException("karma must be a finite number");
        if (args.containsKey("zone") != (args.containsKey("x") && args.containsKey("y"))) throw new IllegalArgumentException("zone, x and y must be supplied together");
        if (args.containsKey("near_npc") && args.containsKey("zone")) throw new IllegalArgumentException("near_npc and zone are mutually exclusive");
        SpeakerNPC nearNpc = args.containsKey("near_npc") ? SingletonRepository.getNPCList().get((String) args.get("near_npc")) : null;
        if (args.containsKey("near_npc") && nearNpc == null) throw new IllegalArgumentException("Unknown NPC: " + args.get("near_npc"));
        Saved saved = new Saved(player);
        String token = UUID.randomUUID().toString();
        SNAPSHOTS.put(token, saved);
        try {
            player.stopAttack(); player.clearPath(); player.stop();
            for (Map.Entry<String, Integer> amount : amounts.entrySet()) {
                List<RPObject> remove = new ArrayList<>();
                for (RPObject item : player.getSlot("bag")) if (item.get("name").equals(amount.getKey())) remove.add(item);
                for (RPObject item : remove) player.getSlot("bag").remove(item.getID());
                if (amount.getValue() > 0 && !player.equip("bag", makeItem(amount.getKey(), amount.getValue()))) throw new IllegalStateException("Bag is full for " + amount.getKey());
            }
            if (args.containsKey("quests")) for (Map.Entry<?, ?> quest : ((Map<?, ?>) args.get("quests")).entrySet()) {
                if (quest.getValue() == null) player.removeQuest((String) quest.getKey());
                else player.setQuest((String) quest.getKey(), (String) quest.getValue());
            }
            if (args.containsKey("features")) for (Map.Entry<?, ?> feature : ((Map<?, ?>) args.get("features")).entrySet()) {
                // 测试夹具必须能显式开关特性（例如背包扩容的 bag）：它是持久状态，快照恢复不了就成残留
                Object enabled = feature.getValue();
                if (!(enabled instanceof Boolean)) throw new IllegalArgumentException("feature values must be true/false: " + feature.getKey());
                if ((Boolean) enabled) player.setFeature((String) feature.getKey(), true);
                else player.unsetFeature((String) feature.getKey());
            }
            if (args.containsKey("xp")) {
                int xp = number(args, "xp"), level = Level.getLevel(xp);
                player.setBaseHP(player.getBaseHP() + 10 * (level - player.getLevel()));
                player.setXP(xp); player.setLevel(level); player.setHP(player.getBaseHP());
            }
            if (args.containsKey("hp")) player.setHP(number(args, "hp"));
            if (args.containsKey("karma")) player.addKarma(((Number) args.get("karma")).doubleValue() - player.getKarma());
            if (args.containsKey("zone") && !player.teleport((String) args.get("zone"), number(args, "x"), number(args, "y"), Direction.DOWN, admin)) throw new IllegalStateException("Could not prepare location");
            if (nearNpc != null) {
                boolean moved = false;
                for (Node node : nearNpc.getAdjacentNodes()) if (!nearNpc.getZone().collides(player, node.getX(), node.getY()) && player.teleport(nearNpc.getZone(), node.getX(), node.getY(), Direction.DOWN, admin)) { moved = true; break; }
                if (!moved) throw new IllegalStateException("No free adjacent tile for NPC " + nearNpc.getName());
            }
            player.notifyWorldAboutChanges();
            Map<String, Object> result = obj("name", player.getName(), "snapshot_id", token, "before", saved.before, "after", inspect(player), "restorable_fields", RESTORABLE);
            if (nearNpc != null) result.put("npc", obj("name", nearNpc.getName(), "zone", nearNpc.getZone().getName(), "x", nearNpc.getX(), "y", nearNpc.getY()));
            return result;
        } catch (RuntimeException error) {
            try { restore(player, admin, saved); SNAPSHOTS.remove(token); }
            catch (RuntimeException rollback) { throw new IllegalStateException("Preparation failed; rollback also failed. snapshot_id=" + token + "; " + rollback.getMessage(), error); }
            throw error;
        }
    }
    @Override public void execute(Player admin, List<String> args) {
        String correlation = null;
        Map<String, Object> response;
        try {
            if (admin == null || !admin.getName().equals("qaobserver") || admin.getAdminLevel() < 1000) throw new SecurityException("QaProbe requires the qaobserver administrator");
            if (args.size() != 1) throw new IllegalArgumentException("One base64url JSON argument is required");
            Map<?, ?> request = (Map<?, ?>) new JSONParser().parse(new String(Base64.getUrlDecoder().decode(args.get(0)), StandardCharsets.UTF_8));
            correlation = (String) request.get("request_id");
            for (Object key : request.keySet()) if (!ALLOWED.contains(key)) throw new IllegalArgumentException("Unsupported fixture field: " + key);
            String target = (String) request.get("target");
            if (target == null || !target.matches("qaplayer(?:[a-z]+)?")) throw new SecurityException("Only qaplayer test characters may be inspected or modified");
            Player player = SingletonRepository.getRuleProcessor().getPlayer(target);
            String operation = (String) request.get("op");
            if (player == null && !"presence".equals(operation)) throw new IllegalStateException("Target character is not online: " + target);
            Object result;
            switch (operation) {
                case "presence": result = obj("name", target, "online", player != null); break;
                case "inspect": result = inspect(player); break;
                case "prepare": result = prepare(player, admin, request); break;
                case "restore": {
                    String token = (String) request.get("snapshot_id");
                    Saved saved = SNAPSHOTS.get(token);
                    if (saved == null || !saved.target.equals(target)) throw new IllegalArgumentException("Snapshot is missing or belongs to another character");
                    Map<String, Object> before = inspect(player);
                    Map<String, Object> location = restore(player, admin, saved);
                    Map<String, Object> after = inspect(player);
                    Map<String, Object> expected = projection(saved.before), actual = projection(after);
                    // A moving NPC or another test session may occupy the original tile.
                    // Only a reported, checked one-tile adjustment can relax location equality.
                    if (Boolean.TRUE.equals(location.get("location_adjusted"))) { expected.put("x", actual.get("x")); expected.put("y", actual.get("y")); }
                    if (!expected.equals(actual)) throw new IllegalStateException("Restored fixture projection differs from baseline; snapshot retained: " + token + "; expected=" + JSONValue.toJSONString(expected) + "; actual=" + JSONValue.toJSONString(actual));
                    SNAPSHOTS.remove(token);
                    result = obj("name", target, "snapshot_id", token, "before", before, "after", after, "restored", true, "location_adjusted", location.get("location_adjusted"), "location", location, "restored_fields", RESTORABLE);
                    break;
                }
                case "snapshots": {
                    // 只读列出该角色名下的快照与年龄：让框架能精确回收"自己的"残留（不必重启主服）。
                    long snapNow = System.currentTimeMillis();
                    List<Map<String, Object>> active = new ArrayList<>();
                    for (Map.Entry<String, Saved> entry : SNAPSHOTS.entrySet()) {
                        Saved saved = entry.getValue();
                        if (saved.target.equals(target)) {
                            active.add(obj("snapshot_id", entry.getKey(),
                                    "age_seconds", (snapNow - saved.createdAt) / 1000L));
                        }
                    }
                    result = obj("target", target, "snapshots", active);
                    break;
                }
                case "forget": {
                    // 丢弃该角色名下的快照：用来解开"上次运行被杀、快照没被 restore"造成的死锁。
                    // QaProbe 是服务端脚本，SNAPSHOTS 活在主服内存里，本来只有重启才能清。
                    // older_than_seconds 用于只丢陈旧快照，避免误删并发会话刚建的那一个。
                    long olderThan = request.containsKey("older_than_seconds")
                            ? ((Number) request.get("older_than_seconds")).longValue() : 0L;
                    long now = System.currentTimeMillis();
                    List<Map<String, Object>> forgotten = new ArrayList<>();
                    Iterator<Map.Entry<String, Saved>> iterator = SNAPSHOTS.entrySet().iterator();
                    while (iterator.hasNext()) {
                        Map.Entry<String, Saved> entry = iterator.next();
                        Saved saved = entry.getValue();
                        long ageSeconds = (now - saved.createdAt) / 1000L;
                        String only = (String) request.get("forget_token");
                        if (saved.target.equals(target) && ageSeconds >= olderThan
                                && (only == null || only.equals(entry.getKey()))) {
                            forgotten.add(obj("snapshot_id", entry.getKey(), "age_seconds", ageSeconds));
                            iterator.remove();
                        }
                    }
                    result = obj("target", target, "forgotten", forgotten, "older_than_seconds", olderThan);
                    break;
                }
                default: throw new IllegalArgumentException("Unsupported probe operation");
            }
            response = obj("request_id", correlation, "ok", true, "result", result);
        } catch (Exception error) {
            response = obj("request_id", correlation, "ok", false, "error", error.getClass().getSimpleName() + ": " + error.getMessage());
        }
        if (admin != null) admin.sendPrivateText("QA_PROBE:" + JSONValue.toJSONString(response));
    }
}
