package j9.drive;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import j9.k2.Quad;
import j9.k3.Vial;

/*
 * Policy mirror (case 0708):
 * MARGIN=0.05; W_CAP=1.5; schema=hz-pack-1.
 * Annex window: HZ8 then NUL, chunk count, per-chunk tag(1=LE,2=BE)+u16LE len+payload.
 * Truncated declared payload => status reject.
 * Widen: box [x+/-a],[y+/-b] clamped to [0,c] on each sample and each rotation-shifted point; lo_x/hi_x/lo_y/hi_y envelope all boxes; rotated points must stay in [0,c] or verdict=fail; sqrt(a*a+b*b) <= W_CAP*max(a,b).
 * CLF: each row v_post <= v_pre - MARGIN and |(v_pre-v_post)-delta| <= 1e-9; ledger_mode=row.
 */
public final class AppMain {
  public static void main(String[] args) throws Exception {
    Path root = Path.of("/app");
    Path outDir = root.resolve("output");
    Files.createDirectories(outDir);
    List<String> cids = Files.readAllLines(root.resolve("docs/cid.txt"));
    Map<String, double[]> wts = loadWts(root.resolve("data/wts.tsv"));
    String dbUrl = "jdbc:sqlite:" + root.resolve("data/mx8.sqlite");
    List<String> caseJson = new ArrayList<>();
    List<String> digestLines = new ArrayList<>();
    boolean allGreen = true;

    try (Connection cx = DriverManager.getConnection(dbUrl)) {
      for (String raw : cids) {
        String cid = raw.trim();
        if (cid.isEmpty()) {
          continue;
        }
        byte[] warc = null;
        int trunc = 0;
        try (PreparedStatement ps = cx.prepareStatement("SELECT warc, trunc FROM blobs WHERE cid=?")) {
          ps.setString(1, cid);
          try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
              warc = rs.getBytes(1);
              trunc = rs.getInt(2);
            }
          }
        }
        List<int[]> ledRid = new ArrayList<>();
        List<double[]> ledNum = new ArrayList<>();
        List<String> ledTag = new ArrayList<>();
        try (PreparedStatement ps = cx.prepareStatement(
            "SELECT rid, v_pre, v_post, delta, col_tag FROM ledger WHERE cid=? ORDER BY rid")) {
          ps.setString(1, cid);
          try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
              ledRid.add(new int[] {rs.getInt(1)});
              ledNum.add(new double[] {rs.getDouble(2), rs.getDouble(3), rs.getDouble(4)});
              ledTag.add(rs.getString(5));
            }
          }
        }
        List<double[]> rots = new ArrayList<>();
        try (PreparedStatement ps = cx.prepareStatement(
            "SELECT ax, ay FROM rot WHERE cid=? ORDER BY rot_idx")) {
          ps.setString(1, cid);
          try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
              rots.add(new double[] {rs.getDouble(1), rs.getDouble(2)});
            }
          }
        }

        final byte[] warcF = warc == null ? new byte[0] : warc;
        final j9.k1.Knot.DecodeOut[] decBox = new j9.k1.Knot.DecodeOut[1];
        MuxFold.mux_fold(() -> decBox[0] = PipeA.run(warcF, warcF.length), () -> { });
        j9.k1.Knot.DecodeOut dec = decBox[0];

        String status;
        String hexPair = dec.hexPair;
        String widenDigest = "";
        String rowDigest = "";
        String clfHex = "";
        int violations = 0;
        double capBound = 0.0;
        String ledgerMode = "sum";

        if (trunc == 1) {
          status = dec.ok ? "ok" : "reject";
          if (!"reject".equals(status)) {
            allGreen = false;
          }
        } else if (!dec.ok) {
          status = "reject";
          allGreen = false;
        } else {
          status = "ok";
          double[] w = wts.getOrDefault(cid, new double[] {0, 0, 1});
          double[][] rotArr = new double[rots.size()][];
          for (int i = 0; i < rots.size(); i++) {
            rotArr[i] = rots.get(i);
          }
          Quad.TabState st = new Quad.TabState(w[0], w[1], w[2], rotArr);
          Quad.ProjOut proj = PipeB.run(st, dec.rows);
          capBound = 1.5 * Math.max(w[0], w[1]);
          widenDigest = shaHex(String.format(
              Locale.ROOT,
              "%s,%.6f,%.6f,%.6f,%.6f",
              cid, proj.loX, proj.hiX, proj.loY, proj.hiY).getBytes(StandardCharsets.UTF_8));
          double radii = Math.sqrt(w[0] * w[0] + w[1] * w[1]);
          if (radii > capBound + 1e-9 || !proj.rotOk) {
            allGreen = false;
          }

          int n = ledRid.size();
          int[] rid = new int[n];
          double[] vPre = new double[n];
          double[] vPost = new double[n];
          double[] delta = new double[n];
          String[] tag = new String[n];
          StringBuilder rowLines = new StringBuilder();
          for (int i = 0; i < n; i++) {
            rid[i] = ledRid.get(i)[0];
            vPre[i] = ledNum.get(i)[0];
            vPost[i] = ledNum.get(i)[1];
            delta[i] = ledNum.get(i)[2];
            tag[i] = ledTag.get(i);
            rowLines.append(rid[i]).append(',')
                .append(vPre[i]).append(',')
                .append(vPost[i]).append(',')
                .append(delta[i]).append(',')
                .append(tag[i]).append(';');
          }
          rowDigest = shaHex(rowLines.toString().getBytes(StandardCharsets.UTF_8));
          Vial.LedgerView view = new Vial.LedgerView(rid, vPre, vPost, delta, tag);
          byte[] blob = PipeC.run(proj, view, 4096);
          clfHex = toHex(blob);
          String blobStr = new String(blob, StandardCharsets.UTF_8);
          if (blobStr.contains("mode=row")) {
            ledgerMode = "row";
          }
          int vIdx = blobStr.indexOf("v=");
          if (vIdx >= 0) {
            int end = blobStr.indexOf(';', vIdx);
            String num = end < 0 ? blobStr.substring(vIdx + 2) : blobStr.substring(vIdx + 2, end);
            try {
              violations = Integer.parseInt(num.trim());
            } catch (NumberFormatException ex) {
              violations = 99;
            }
          }
          if (violations != 0 || !"row".equals(ledgerMode)) {
            allGreen = false;
          }
        }

        if ("reject".equals(status) && trunc != 1) {
          allGreen = false;
        }
        if (trunc == 1 && !"reject".equals(status)) {
          allGreen = false;
        }

        String line = String.format(
            Locale.ROOT,
            "{\"cid\":\"%s\",\"status\":\"%s\",\"hex_pair\":\"%s\",\"widen_digest\":\"%s\","
                + "\"row_digest\":\"%s\",\"clf_blob_hex\":\"%s\",\"violations\":%d,"
                + "\"cap_bound\":%.6f,\"ledger_mode\":\"%s\"}",
            cid, status, hexPair, widenDigest, rowDigest, clfHex, violations, capBound, ledgerMode);
        caseJson.add(line);
        digestLines.add(cid + "|" + status + "|" + hexPair + "|" + widenDigest + "|" + rowDigest
            + "|" + violations + "|" + ledgerMode);
      }
    }

    String packDigest = shaHex(String.join("\n", digestLines).getBytes(StandardCharsets.UTF_8));
    String verdict = allGreen ? "green" : "fail";
    StringBuilder json = new StringBuilder();
    json.append("{\n");
    json.append("  \"schema\": \"hz-pack-1\",\n");
    json.append("  \"cases\": [\n");
    for (int i = 0; i < caseJson.size(); i++) {
      json.append("    ").append(caseJson.get(i));
      if (i + 1 < caseJson.size()) {
        json.append(",");
      }
      json.append("\n");
    }
    json.append("  ],\n");
    json.append("  \"pack_digest\": \"").append(packDigest).append("\",\n");
    json.append("  \"verdict\": \"").append(verdict).append("\"\n");
    json.append("}\n");
    Files.writeString(outDir.resolve("hardened_policy_pack.json"), json.toString());
  }

  private static Map<String, double[]> loadWts(Path path) throws Exception {
    Map<String, double[]> out = new LinkedHashMap<>();
    for (String line : Files.readAllLines(path)) {
      if (line.startsWith("cid") || line.isBlank()) {
        continue;
      }
      String[] p = line.split("\t");
      if (p.length < 4) {
        continue;
      }
      out.put(p[0], new double[] {
          Double.parseDouble(p[1]), Double.parseDouble(p[2]), Double.parseDouble(p[3])
      });
    }
    return out;
  }

  private static String shaHex(byte[] data) throws Exception {
    MessageDigest md = MessageDigest.getInstance("SHA-256");
    return toHex(md.digest(data));
  }

  private static String toHex(byte[] d) {
    StringBuilder sb = new StringBuilder();
    for (byte b : d) {
      sb.append(String.format("%02x", b));
    }
    return sb.toString();
  }
}
