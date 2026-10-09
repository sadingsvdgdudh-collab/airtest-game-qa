package games.stendhal.server.script;

import java.nio.charset.StandardCharsets;
import java.util.*;
import games.stendhal.server.core.engine.SingletonRepository;
import games.stendhal.server.core.engine.StendhalRPZone;
import games.stendhal.server.core.scripting.ScriptImpl;
import games.stendhal.server.entity.creature.Creature;
import games.stendhal.server.entity.item.Corpse;
import games.stendhal.server.entity.player.Player;
import marauroa.common.game.RPObject;
import org.json.simple.JSONValue;
import org.json.simple.parser.JSONParser;

/** Local fixture only: unchanged rat AI/stats; captures the corpse identity for cleanup. */
public final class QaCombat extends ScriptImpl {
    private static final Map<String, Fixture> FIXTURES = new HashMap<>();
    private static final Set<String> ALLOWED = Set.of("request_id", "op", "target", "timeout_ms", "fixture_id", "placement");
    private static final class Rat extends Creature {
        Corpse corpse;
        Rat() { super(SingletonRepository.getEntityManager().getCreature("rat")); }
        @Override protected Corpse makeCorpse(String killer) {
            corpse = super.makeCorpse(killer);
            return corpse;
        }
    }
    private static final class Fixture {
        final String target;
        final Rat rat;
        final StendhalRPZone zone;
        Fixture(Player player, Rat rat) { target = player.getName(); this.rat = rat; zone = player.getZone(); }
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
    private static boolean present(StendhalRPZone zone, RPObject object) {
        return object != null && zone.has(object.getID()) && zone.get(object.getID()) == object;
    }
    private static Map<String, Object> inspect(String id, Fixture fixture, Player player) {
        return obj("name", fixture.target, "fixture_id", id, "zone", fixture.zone.getName(),
            "rat_present", present(fixture.zone, fixture.rat), "rat", attributes(fixture.rat),
            "corpse_present", present(fixture.zone, fixture.rat.corpse),
            "corpse", fixture.rat.corpse == null ? null : attributes(fixture.rat.corpse),
            "turn", SingletonRepository.getRuleProcessor().getTurn(),
            "next_to", player.nextTo(fixture.rat), "squared_distance", player.squaredDistance(fixture.rat),
            "range", player.getMaxRangeForArcher(), "attack_rate", player.getAttackRate(),
            "target_fixture", player.getAttackTarget() == fixture.rat);
    }
    private static Map<String, Object> layout(Player player) {
        StendhalRPZone zone = player.getZone();
        Object free = null;
        for (int[] delta : List.of(new int[]{1,0}, new int[]{0,1}, new int[]{-1,0}, new int[]{0,-1})) {
            int x = player.getX() + delta[0], y = player.getY() + delta[1];
            if (!zone.collides(player, x, y)) { free = obj("x", x, "y", y); break; }
        }
        if (free == null) throw new IllegalStateException("No free adjacent tile for movement control");
        return obj("name", player.getName(), "zone", zone.getName(), "width", zone.getWidth(), "height", zone.getHeight(), "adjacent_free", free);
    }
    private static Object prepare(Player player, String placement) {
        for (Fixture fixture : FIXTURES.values()) if (fixture.target.equals(player.getName())) throw new IllegalStateException("Clean the active combat fixture first");
        if (!player.getZone().getName().equals("int_semos_guard_house")) throw new IllegalArgumentException("Combat fixture is restricted to int_semos_guard_house");
        // One fresh rat kill cannot reach Rat Hunter (15) or Exterminator (10).
        if (player.getAllKillCount("rat") >= 9) throw new IllegalStateException("Rat kill baseline too high for a fixture that does not restore achievements");
        Rat rat = new Rat();
        boolean placed = false;
        List<Integer> distances = placement.equals("far") ? List.of(10, 9, 8) : List.of(3, 4, 2);
        for (int distance : distances) for (int[] delta : List.of(new int[]{distance,0}, new int[]{0,distance}, new int[]{-distance,0}, new int[]{0,-distance})) {
            int x = player.getX() + delta[0], y = player.getY() + delta[1];
            if (!placed && !player.getZone().collides(rat, x, y)) {
                boolean safe = true;
                for (RPObject object : player.getZone()) if (object instanceof Player && object != player && ((Player) object).squaredDistance(x, y) < 64) safe = false;
                if (safe) { rat.setPosition(x, y); placed = true; }
            }
        }
        if (!placed) throw new IllegalStateException("No unoccupied rat tile clear of other players");
        String id = UUID.randomUUID().toString();
        Fixture fixture = new Fixture(player, rat);
        fixture.zone.add(rat); FIXTURES.put(id, fixture);
        return inspect(id, fixture, player);
    }
    @Override public void execute(Player admin, List<String> args) {
        String correlation = null;
        Map<String, Object> response;
        try {
            if (admin == null || !admin.getName().equals("qaobserver") || admin.getAdminLevel() < 1000) throw new SecurityException("QaCombat requires qaobserver administrator");
            if (args.size() != 1) throw new IllegalArgumentException("One base64url JSON argument is required");
            Map<?, ?> request = (Map<?, ?>) new JSONParser().parse(new String(Base64.getUrlDecoder().decode(args.get(0)), StandardCharsets.UTF_8));
            correlation = (String) request.get("request_id");
            for (Object key : request.keySet()) if (!ALLOWED.contains(key)) throw new IllegalArgumentException("Unsupported combat fixture field: " + key);
            String target = (String) request.get("target");
            if (target == null || !(target.equals("qaplayer") || target.matches("qaplayer[a-z]+"))) throw new SecurityException("Only dedicated UI/API test characters may use combat fixtures");
            Player player = SingletonRepository.getRuleProcessor().getPlayer(target);
            if (player == null) throw new IllegalStateException("Target character is not online: " + target);
            String op = (String) request.get("op");
            if (request.containsKey("placement") && !"prepare".equals(op)) throw new IllegalArgumentException("placement is only valid for combat prepare");
            String placement = request.containsKey("placement") ? (String) request.get("placement") : "near";
            if (!"near".equals(placement) && !"far".equals(placement)) throw new IllegalArgumentException("placement must be near or far");
            Object result;
            if (op.equals("prepare")) result = prepare(player, placement);
            else if (op.equals("layout")) result = layout(player);
              else if (op.equals("cleanup_all")) {
                  // 清掉该角色名下的**全部**战斗夹具：一次中断会让夹具留在服务端内存里
                  // （"Clean the active combat fixture first"），以前只能重启主服。
                  java.util.List<String> cleaned = new java.util.ArrayList<>();
                  java.util.Iterator<java.util.Map.Entry<String, Fixture>> it = FIXTURES.entrySet().iterator();
                  while (it.hasNext()) {
                      java.util.Map.Entry<String, Fixture> entry = it.next();
                      Fixture f = entry.getValue();
                      if (!f.target.equals(target)) continue;
                      player.stopAttack(); player.clearPath(); player.stop();
                      f.rat.stopAttack(); f.rat.clearPath(); f.rat.stop();
                      if (present(f.zone, f.rat)) f.zone.remove(f.rat);
                      if (present(f.zone, f.rat.corpse)) f.zone.remove(f.rat.corpse);
                      cleaned.add(entry.getKey());
                      it.remove();
                  }
                  result = obj("target", target, "cleaned", cleaned);
              }
            else {
                String id = (String) request.get("fixture_id");
                Fixture fixture = FIXTURES.get(id);
                if (fixture == null || !fixture.target.equals(target)) throw new IllegalArgumentException("Fixture missing or owned by another player");
                if (op.equals("inspect")) result = inspect(id, fixture, player);
                else if (op.equals("cleanup")) {
                    player.stopAttack(); player.clearPath(); player.stop();
                    fixture.rat.stopAttack(); fixture.rat.clearPath(); fixture.rat.stop();
                    if (present(fixture.zone, fixture.rat)) fixture.zone.remove(fixture.rat);
                    if (present(fixture.zone, fixture.rat.corpse)) fixture.zone.remove(fixture.rat.corpse);
                    result = inspect(id, fixture, player);
                    FIXTURES.remove(id);
                } else throw new IllegalArgumentException("Unsupported combat fixture operation");
            }
            response = obj("request_id", correlation, "ok", true, "result", result);
        } catch (Exception error) {
            response = obj("request_id", correlation, "ok", false, "error", error.getClass().getSimpleName() + ": " + error.getMessage());
        }
        if (admin != null) admin.sendPrivateText("QA_PROBE:" + JSONValue.toJSONString(response));
    }
}
