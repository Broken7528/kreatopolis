package link.infra.packwiz.installer.bootstrap;

import com.eclipsesource.json.Json;
import com.eclipsesource.json.JsonArray;
import com.eclipsesource.json.JsonObject;
import com.eclipsesource.json.JsonValue;
import com.eclipsesource.json.WriterConfig;

import javax.swing.JDialog;
import javax.swing.JOptionPane;
import javax.swing.UIManager;
import java.awt.GraphicsEnvironment;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.Reader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * PolyMC-aware wrapper around packwiz-installer-bootstrap.
 *
 * 1. Automatically passes --multimc-folder <pack-folder> to packwiz-installer so its Prism-only
 *    ("net.neoforged") updater never corrupts PolyMC's mmc-pack.json.
 * 2. Compares the remote pack.toml [versions] against the PolyMC instance's ../mmc-pack.json and
 *    ../patches/net.neoforged.neoforge.json. If NeoForge (or Minecraft) changed—or if mmc-pack.json
 *    has broken component ordering—it updates mmc-pack.json + patches/net.neoforged.neoforge.json,
 *    alerts the player with a popup dialog, and exits with code 1 so PolyMC aborts the launch until
 *    reloaded.
 */
public class KreatopolisBootstrap {

    private static final String NEOFORGE_UID = "net.neoforged.neoforge";
    private static final String MINECRAFT_UID = "net.minecraft";
    private static final String LWJGL_UID = "org.lwjgl3";
    private static final String PRISM_NEOFORGE_UID = "net.neoforged";

    public static void main(String[] args) {
        Path packFolder = Paths.get(".");
        String packUrl = null;
        boolean hasMultiMcFolder = false;
        boolean isClient = true;

        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            if (("--pack-folder".equals(a) || "-p".equals(a)) && i + 1 < args.length) {
                packFolder = Paths.get(args[++i]);
            } else if ("--multimc-folder".equals(a) && i + 1 < args.length) {
                hasMultiMcFolder = true;
                i++;
            } else if (("--side".equals(a) || "-s".equals(a)) && i + 1 < args.length) {
                isClient = !"server".equalsIgnoreCase(args[++i]);
            } else if ((a.startsWith("http://") || a.startsWith("https://"))
                    && (i == 0 || !"--bootstrap-update-url".equals(args[i - 1]))) {
                packUrl = a;
            }
        }

        if (isClient && packUrl != null) {
            checkAndSyncPolyMcLoader(packFolder, packUrl);
        }

        String[] childArgs = args;
        if (isClient && !hasMultiMcFolder && args.length > 0) {
            List<String> list = new ArrayList<String>();
            for (int i = 0; i < args.length - 1; i++) {
                list.add(args[i]);
            }
            list.add("--multimc-folder");
            list.add(packFolder.toString());
            list.add(args[args.length - 1]);
            childArgs = list.toArray(new String[0]);
        }

        Main.main(childArgs);
    }

    private static void checkAndSyncPolyMcLoader(Path packFolder, String packUrl) {
        try {
            Path instanceDir = packFolder.toAbsolutePath().normalize().getParent();
            if (instanceDir == null) {
                return;
            }
            Path mmcPackPath = instanceDir.resolve("mmc-pack.json");
            if (!Files.exists(mmcPackPath)) {
                return;
            }

            String packToml = fetchUrl(packUrl);
            String targetMc = extractTomlVersion(packToml, "minecraft");
            String targetNeo = extractTomlVersion(packToml, "neoforge");
            if (targetMc == null || targetNeo == null) {
                return;
            }

            JsonObject mmcPack;
            try (Reader r = Files.newBufferedReader(mmcPackPath, StandardCharsets.UTF_8)) {
                mmcPack = Json.parse(r).asObject();
            }

            JsonValue compsVal = mmcPack.get("components");
            JsonArray comps = (compsVal != null && compsVal.isArray()) ? compsVal.asArray() : new JsonArray();

            int mcIdx = -1;
            int neoIdx = -1;
            String curMc = null;
            String curNeo = null;
            boolean hasPrismUid = false;

            for (int i = 0; i < comps.size(); i++) {
                JsonValue v = comps.get(i);
                if (!v.isObject()) continue;
                JsonObject obj = v.asObject();
                String uid = obj.getString("uid", "");
                if (MINECRAFT_UID.equals(uid)) {
                    mcIdx = i;
                    curMc = obj.getString("version", null);
                } else if (NEOFORGE_UID.equals(uid)) {
                    neoIdx = i;
                    curNeo = obj.getString("version", null);
                } else if (PRISM_NEOFORGE_UID.equals(uid)) {
                    hasPrismUid = true;
                }
            }

            Path patchPath = instanceDir.resolve("patches").resolve(NEOFORGE_UID + ".json");
            boolean patchValid = false;
            if (Files.exists(patchPath)) {
                try (Reader r = Files.newBufferedReader(patchPath, StandardCharsets.UTF_8)) {
                    JsonObject patchObj = Json.parse(r).asObject();
                    patchValid = targetNeo.equals(patchObj.getString("version", null));
                } catch (Exception ignored) {
                    patchValid = false;
                }
            }

            boolean versionChanged = !targetNeo.equals(curNeo) || !targetMc.equals(curMc);
            boolean orderBroken = (mcIdx == -1 || neoIdx == -1 || neoIdx < mcIdx || hasPrismUid);

            if (!versionChanged && !orderBroken && patchValid) {
                return;
            }

            // Fetch official PolyMC patch JSON for the target NeoForge version
            String patchUrl = "https://meta.polymc.org/v1/" + NEOFORGE_UID + "/" + targetNeo + ".json";
            String patchJson = fetchUrl(patchUrl);
            if (patchJson != null && !patchJson.isEmpty()) {
                Files.createDirectories(patchPath.getParent());
                Files.write(patchPath, patchJson.getBytes(StandardCharsets.UTF_8));
            }

            // Write clean, properly ordered mmc-pack.json (LWJGL 3 -> Minecraft -> NeoForge)
            JsonObject newMmcPack = buildCleanMmcPack(targetMc, targetNeo);
            String prettyJson = newMmcPack.toString(WriterConfig.PRETTY_PRINT) + "\n";
            Files.write(mmcPackPath, prettyJson.getBytes(StandardCharsets.UTF_8));

            String detail = (curNeo != null && !curNeo.equals(targetNeo))
                    ? "NeoForge was updated to " + targetNeo + " (was " + curNeo + ")."
                    : "NeoForge loader configuration was updated to " + targetNeo + ".";
            String message = detail + "\n\n"
                    + "Please restart PolyMC (or click Edit -> Version -> Reload)\n"
                    + "and click Launch again.";

            System.err.println("[Kreatopolis] " + message.replace('\n', ' '));
            showPopup(message);
            System.exit(1);
        } catch (Exception e) {
            System.err.println("[Kreatopolis] Warning during NeoForge version check: " + e.getMessage());
        }
    }

    private static JsonObject buildCleanMmcPack(String mc, String neo) {
        JsonObject lwjgl = Json.object()
                .add("cachedName", "LWJGL 3")
                .add("cachedVersion", "3.3.3")
                .add("cachedVolatile", true)
                .add("dependencyOnly", true)
                .add("uid", LWJGL_UID)
                .add("version", "3.3.3");

        JsonObject minecraft = Json.object()
                .add("cachedName", "Minecraft")
                .add("cachedRequires", Json.array().add(
                        Json.object().add("suggests", "3.3.3").add("uid", LWJGL_UID)))
                .add("cachedVersion", mc)
                .add("important", true)
                .add("uid", MINECRAFT_UID)
                .add("version", mc);

        JsonObject neoforge = Json.object()
                .add("cachedName", "NeoForge")
                .add("cachedRequires", Json.array().add(
                        Json.object().add("equals", mc).add("uid", MINECRAFT_UID)))
                .add("cachedVersion", neo)
                .add("uid", NEOFORGE_UID)
                .add("version", neo);

        return Json.object()
                .add("components", Json.array().add(lwjgl).add(minecraft).add(neoforge))
                .add("formatVersion", 1);
    }

    private static void showPopup(String message) {
        if (GraphicsEnvironment.isHeadless()) {
            return;
        }
        try {
            UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
        } catch (Exception ignored) {
        }
        JOptionPane pane = new JOptionPane(message, JOptionPane.INFORMATION_MESSAGE);
        JDialog dialog = pane.createDialog(null, "Kreatopolis — NeoForge Updated");
        dialog.setAlwaysOnTop(true);
        dialog.setModal(true);
        dialog.setVisible(true);
        dialog.dispose();
    }

    private static String extractTomlVersion(String toml, String key) {
        Pattern p = Pattern.compile("(?m)^\\s*" + Pattern.quote(key) + "\\s*=\\s*\"([^\"]+)\"");
        Matcher m = p.matcher(toml);
        return m.find() ? m.group(1) : null;
    }

    private static String fetchUrl(String urlStr) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setRequestProperty("User-Agent", "kreatopolis-bootstrap/1.0");
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line).append('\n');
            }
            return sb.toString();
        }
    }
}
