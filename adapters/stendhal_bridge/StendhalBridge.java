/* Local test client. Uses the official Marauroa protocol implementation. */
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.BooleanSupplier;
import marauroa.client.ClientFramework;
import marauroa.client.net.*;
import marauroa.common.game.*;
import marauroa.common.net.message.*;
import org.json.simple.*;
import org.json.simple.parser.JSONParser;

public final class StendhalBridge extends ClientFramework implements IPerceptionListener {
    private final Object stateLock = new Object();
    private final Map<RPObject.ID, RPObject> world = new HashMap<>();
    private final PerceptionHandler perceptions = new PerceptionHandler(this);
    private final Map<String, Object> replies = new HashMap<>();
    private final List<Map<String, Object>> events = new ArrayList<>();
    private final List<Map<String, Object>> chatMessages = new ArrayList<>();
    private String[] characters = new String[0];
    private String character;
    private volatile boolean selected;
    private boolean loggedIn;
    private volatile boolean running = true;
    private volatile String perceptionError;
    private int timestamp;

    static Map<String, Object> obj(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) result.put((String) values[i], values[i + 1]);
        return result;
    }
    static String required(Map<?, ?> args, String key) {
        Object value = args.get(key);
        if (!(value instanceof String) || ((String) value).isBlank()) throw new IllegalArgumentException("Missing string: " + key);
        return (String) value;
    }
    static int integer(Map<?, ?> args, String key, int fallback) {
        return args.containsKey(key) ? ((Number) args.get(key)).intValue() : fallback;
    }
    static Map<String, Object> state(RPObject object) {
        Map<String, Object> attributes = new LinkedHashMap<>(), slots = new LinkedHashMap<>();
        for (String key : object) attributes.put(key, object.get(key));
        for (RPSlot slot : object.slots()) {
            List<Object> items = new ArrayList<>();
            for (RPObject item : slot) items.add(state(item));
            slots.put(slot.getName(), items);
        }
        return obj("name", object.has("name") ? object.get("name") : null, "attributes", attributes, "slots", slots);
    }
    private void await(BooleanSupplier predicate, int timeoutMs) throws Exception {
        long deadline = System.nanoTime() + timeoutMs * 1_000_000L;
        while (!predicate.getAsBoolean()) {
            if (perceptionError != null) throw new IOException("Perception failed: " + perceptionError);
            if (!getConnectionState()) throw new IOException("Game connection closed");
            if (System.nanoTime() >= deadline) throw new java.util.concurrent.TimeoutException("No matching server state within " + timeoutMs + " ms");
            Thread.sleep(30);
        }
    }
    private Map<String, Object> selfState() {
        synchronized (stateLock) {
            for (RPObject object : world.values()) if (object.has("name") && object.get("name").equals(character)) {
                Map<String, Object> result = state(object);
                result.put("perception_timestamp", timestamp);
                result.put("character", character);
                return result;
            }
            return null;
        }
    }
    private Object probe(String operation, Map<?, ?> args) throws Exception {
        if (!selected) throw new IllegalStateException("Select observer character before using the probe");
        String target = required(args, "target");
        if (target.equals(character)) throw new IllegalArgumentException("Probe must use a separate observer character");
        String correlation = UUID.randomUUID().toString();
        Map<String, Object> payload = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : args.entrySet()) payload.put((String) entry.getKey(), entry.getValue());
        payload.put("op", operation.startsWith("combat_") ? operation.substring(7) : operation);
        payload.put("request_id", correlation);
        String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(JSONValue.toJSONString(payload).getBytes(StandardCharsets.UTF_8));
        RPAction action = new RPAction();
        action.put("type", "script"); action.put("target", operation.startsWith("combat_") ? "QaCombat.class" : "QaProbe.class"); action.put("args", encoded);
        send(action);
        await(() -> { synchronized (stateLock) { return replies.containsKey(correlation); } }, integer(args, "timeout_ms", 10000));
        Map<?, ?> response;
        synchronized (stateLock) { response = (Map<?, ?>) replies.remove(correlation); }
        if (!Boolean.TRUE.equals(response.get("ok"))) throw new IllegalStateException(String.valueOf(response.get("error")));
        Object result = response.get("result");
        if (result instanceof Map && ((Map<?, ?>) result).containsKey("name") && !target.equals(((Map<?, ?>) result).get("name"))) throw new IOException("Target identity mismatch");
        return result;
    }
    private Object request(String operation, Map<?, ?> args) throws Exception {
        switch (operation) {
            case "connect": {
                if (getConnectionState()) throw new IllegalStateException("Already connected; disconnect first");
                String host = String.valueOf(args.containsKey("host") ? args.get("host") : "127.0.0.1");
                // This helper is intentionally limited to the isolated local test server.
                if (!InetAddress.getByName(host).isLoopbackAddress()) throw new IllegalArgumentException("Only loopback test servers are allowed");
                int port = integer(args, "port", 32160);
                connect(host, port);
                return obj("connected", getConnectionState(), "host", host, "port", port);
            }
            case "create_account": {
                AccountResult result = createAccount(required(args, "username"), required(args, "password"), String.valueOf(args.containsKey("email") ? args.get("email") : ""));
                if (result.failed()) throw new IllegalStateException(result.toString());
                return obj("username", result.getUsername(), "status", result.getResult().toString());
            }
            case "login": {
                if (selected) throw new IllegalStateException("Disconnect before another login");
                login(required(args, "username"), required(args, "password"));
                loggedIn = true;
                if (args.containsKey("character")) select(required(args, "character"), integer(args, "timeout_ms", 15000));
                return obj("characters", Arrays.asList(characters), "character", character, "selected", selected);
            }
            case "create_character": {
                if (!loggedIn) throw new IllegalStateException("Login before creating a character");
                CharacterResult result = createCharacter(required(args, "character"), new RPObject());
                if (result.getResult().failed()) throw new IllegalStateException(result.toString());
                return obj("status", result.getResult().toString(), "character", result.getCharacter(), "characters", Arrays.asList(characters));
            }
            case "choose_character": select(required(args, "character"), integer(args, "timeout_ms", 15000)); return selfState();
            case "get_self_state": {
                if (!selected) throw new IllegalStateException("No selected character");
                if (!getConnectionState()) throw new IOException("Game connection closed");
                if (perceptionError != null) throw new IOException("Perception failed: " + perceptionError);
                Map<String, Object> result = selfState();
                if (result == null) throw new IOException("No perception for selected character");
                return result;
            }
            case "presence": case "inspect": case "prepare": case "restore": case "forget": case "snapshots":
            case "combat_prepare": case "combat_inspect": case "combat_cleanup": case "combat_layout": case "combat_cleanup_all": return probe(operation, args);
            case "send_action": {
                if (!selected) throw new IllegalStateException("No selected character");
                Map<?, ?> fields = (Map<?, ?>) args.get("action");
                if (fields == null || !fields.containsKey("type")) throw new IllegalArgumentException("action.type is required");
                RPAction action = new RPAction();
                for (Map.Entry<?, ?> field : fields.entrySet()) action.put((String) field.getKey(), String.valueOf(field.getValue()));
                send(action);
                return obj("sent", true, "note", "Queued by SDK; verify server state separately");
            }
            case "get_events": synchronized (stateLock) { List<Object> result = new ArrayList<>(events); events.clear(); return result; }
            case "get_chat_messages": synchronized (stateLock) { List<Object> result = new ArrayList<>(chatMessages); chatMessages.clear(); return result; }
            case "get_world_state": synchronized (stateLock) { List<Object> result = new ArrayList<>(); for (RPObject object : world.values()) result.add(state(object)); return result; }
            case "disconnect": selected = false; loggedIn = false; close(); synchronized (stateLock) { world.clear(); replies.clear(); events.clear(); chatMessages.clear(); } character = null; return obj("disconnected", true);
            default: throw new IllegalArgumentException("Unsupported operation: " + operation);
        }
    }
    private void select(String name, int timeoutMs) throws Exception {
        if (selected) throw new IllegalStateException("A character is already selected");
        if (!loggedIn) throw new IllegalStateException("Login before selecting a character");
        if (!chooseCharacter(name)) throw new IllegalStateException("Server rejected character " + name);
        character = name; selected = true;
        await(() -> selfState() != null, timeoutMs);
    }
    private void collect(RPObject object, RPObject original) {
        if (object == null) return;
        for (RPEvent event : object.events()) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("event", event.getName());
            for (String key : event) entry.put(key, event.get(key));
            String name = object.has("name") ? object.get("name") : original != null && original.has("name") ? original.get("name") : null;
            String type = object.has("type") ? object.get("type") : original != null && original.has("type") ? original.get("type") : null;
            entry.put("source_name", name); entry.put("source_type", type); entry.put("perception_timestamp", timestamp);
            events.add(entry);
            if (events.size() > 100) events.remove(0);
            if (event.getName().equals("text") && event.has("text")) {
                chatMessages.add(obj("name", name, "type", type, "text", event.get("text"), "perception_timestamp", timestamp));
                if (chatMessages.size() > 100) chatMessages.remove(0);
            }
            if (event.has("text") && event.get("text").startsWith("QA_PROBE:")) {
                try {
                    Map<?, ?> response = (Map<?, ?>) new JSONParser().parse(event.get("text").substring(9));
                    replies.put((String) response.get("request_id"), response);
                } catch (Exception exception) { perceptionError = "Invalid probe response: " + exception; }
            }
        }
    }
    private void collectChat(RPObject original, RPObject changes) {
        if (changes == null || !changes.has("text") || changes.get("text").isEmpty()) return;
        String name = changes.has("name") ? changes.get("name") : original != null && original.has("name") ? original.get("name") : null;
        String type = changes.has("type") ? changes.get("type") : original != null && original.has("type") ? original.get("type") : null;
        chatMessages.add(obj("name", name, "type", type, "text", changes.get("text"), "perception_timestamp", timestamp));
        if (chatMessages.size() > 100) chatMessages.remove(0);
    }
    @Override protected void onPerception(MessageS2CPerception message) {
        synchronized (stateLock) {
            try { perceptions.apply(message, world); } catch (Exception exception) { perceptionError = exception.toString(); }
        }
    }
    @Override protected String getGameName() { return "stendhal"; }
    @Override protected String getVersionNumber() { return "1.49"; }
    @Override protected List<TransferContent> onTransferREQ(List<TransferContent> items) { return items; }
    @Override protected void onTransfer(List<TransferContent> items) {}
    @Override protected void onAvailableCharacters(String[] available) { characters = available; }
    @Override protected void onServerInfo(String[] info) { System.err.println("Server info: " + Arrays.toString(info)); }
    @Override protected void onPreviousLogins(List<String> previous) {}
    @Override public boolean onAdded(RPObject object) { collect(object, object); collectChat(object, object); return false; }
    @Override public boolean onModifiedAdded(RPObject object, RPObject changes) { collect(changes, object); collectChat(object, changes); return false; }
    @Override public boolean onModifiedDeleted(RPObject object, RPObject changes) { return false; }
    @Override public boolean onDeleted(RPObject object) { return false; }
    @Override public boolean onMyRPObject(RPObject added, RPObject deleted) { collect(added, added == null ? null : world.get(added.getID())); return false; }
    @Override public boolean onClear() { return false; }
    @Override public void onSynced() {}
    @Override public void onUnsynced() { resync(); }
    @Override public void onPerceptionBegin(byte type, int time) { timestamp = time; }
    @Override public void onPerceptionEnd(byte type, int time) { timestamp = time; }
    @Override public void onException(Exception exception, MessageS2CPerception perception) { perceptionError = exception.toString(); }

    public static void main(String[] arguments) throws Exception {
        PrintStream protocol = System.out;
        System.setOut(System.err); // Third-party console output cannot corrupt JSONL.
        StendhalBridge client = new StendhalBridge();
        Thread pump = new Thread(() -> {
            while (client.running) {
                try { if (client.selected) client.loop(0); Thread.sleep(30); }
                catch (Exception exception) { client.perceptionError = exception.toString(); }
            }
        }, "stendhal-perceptions");
        pump.setDaemon(true); pump.start();
        try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = input.readLine()) != null) {
                Object id = null;
                Map<String, Object> response;
                try {
                    Map<?, ?> request = (Map<?, ?>) new JSONParser().parse(line);
                    id = request.get("id");
                    Map<?, ?> args = request.get("args") == null ? Collections.emptyMap() : (Map<?, ?>) request.get("args");
                    response = obj("id", id, "ok", true, "result", client.request(required(request, "op"), args));
                } catch (Exception exception) {
                    exception.printStackTrace(System.err);
                    response = obj("id", id, "ok", false, "error", obj("type", exception.getClass().getSimpleName(), "message", String.valueOf(exception.getMessage())));
                }
                protocol.println(JSONValue.toJSONString(response)); protocol.flush();
            }
        } finally { client.running = false; client.selected = false; client.close(); }
    }
}
