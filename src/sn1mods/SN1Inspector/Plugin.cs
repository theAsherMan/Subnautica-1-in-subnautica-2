using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using BepInEx;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SN1Inspector
{
    // File-command inspector for Subnautica 1. I/O folder: <SN1Dir>/BepInEx/SN1Inspector/
    //   status.txt  rewritten ~every 0.5 s (atomic)
    //   cmd.txt     "<id> <verb> [args]" per line; read, then deleted by the mod; each id runs once
    //   out.txt     "<id> OK|ERR <text>" appended
    // Never triggers a save. Quit = Application.Quit() (no save path).
    [BepInPlugin("sn1inspector", "SN1Inspector", "0.1.0")]
    public class Plugin : BaseUnityPlugin
    {
        string io, statusPath, cmdPath, outPath;
        float nextStatus, nextCmd;
        int framesSince; float timeSince; float fps;
        readonly HashSet<string> done = new HashSet<string>();
        bool newGameSession;
        string pendingId; // id of the command being run; verbs that reply later return null and call Out(id, ...) themselves
        static readonly CultureInfo IC = CultureInfo.InvariantCulture;

        void Awake()
        {
            io = Path.Combine(Paths.BepInExRootPath, "SN1Inspector");
            Directory.CreateDirectory(io);
            statusPath = Path.Combine(io, "status.txt");
            cmdPath = Path.Combine(io, "cmd.txt");
            outPath = Path.Combine(io, "out.txt");
            Logger.LogInfo("SN1Inspector loaded, io folder " + io);
        }

        void Update()
        {
            framesSince++; timeSince += Time.unscaledDeltaTime;
            float now = Time.realtimeSinceStartup;
            if (now >= nextCmd) { nextCmd = now + 0.2f; try { PollCommands(); } catch (Exception e) { Logger.LogWarning("poll: " + e); } }
            if (now >= nextStatus)
            {
                nextStatus = now + 0.5f;
                if (timeSince > 0f) fps = framesSince / timeSince;
                framesSince = 0; timeSince = 0f;
                try { WriteStatus(); } catch (Exception e) { Logger.LogWarning("status: " + e); }
            }
        }

        // ---- state helpers -------------------------------------------------
        string GameState()
        {
            if (uGUI_MainMenu.main != null) return "menu";
            var p = Player.main;
            var s = LargeWorldStreamer.main;
            if (p != null && s != null && s.IsReady() && s.IsWorldSettled() && !WaitScreen.IsWaiting) return "ingame";
            return "loading";
        }

        string GameModeStr()
        {
            try
            {
                GameModeOption m, c;
                GameModeUtils.GetGameMode(out m, out c);
                return m + (c != GameModeOption.None ? "+cheats:" + c : "");
            }
            catch (Exception e) { return "?" + e.GetType().Name; }
        }

        static string F(float v) { return v.ToString("0.00", IC); }

        string PosStr()
        {
            var p = Player.main;
            if (p == null) return "none";
            Vector3 v = p.transform.position;
            return "x=" + F(v.x) + " y=" + F(v.y) + " z=" + F(v.z) + " " + CamStr();
        }

        string CamStr()
        {
            Camera c = Camera.main;
            if (c == null) return "yaw=? pitch=?";
            Vector3 e = c.transform.eulerAngles;
            float pitch = e.x > 180f ? e.x - 360f : e.x;
            return "yaw=" + F(e.y) + " pitch=" + F(pitch);
        }

        string BatchStr()
        {
            var s = LargeWorldStreamer.main; var p = Player.main;
            if (s == null || p == null) return "none";
            var b = s.GetContainingBatch(p.transform.position);
            return b.x + "-" + b.y + "-" + b.z;
        }

        string BiomeStr() { var p = Player.main; return p == null ? "none" : p.GetBiomeString(); }

        void WriteStatus()
        {
            var sb = new StringBuilder();
            string state = GameState();
            sb.AppendLine("utc=" + DateTime.UtcNow.ToString("o", IC));
            sb.AppendLine("frame=" + Time.frameCount);
            sb.AppendLine("fps=" + F(fps));
            sb.AppendLine("scene=" + SceneManager.GetActiveScene().name);
            sb.AppendLine("state=" + state);
            sb.AppendLine("gamemode=" + (state == "menu" ? "n/a" : GameModeStr()));
            sb.AppendLine("newgame_session=" + newGameSession);
            if (state == "ingame")
            {
                sb.AppendLine("pos=" + PosStr());
                sb.AppendLine("depth=" + F(Player.main.GetDepth()));
                sb.AppendLine("biome=" + BiomeStr());
                sb.AppendLine("batch=" + BatchStr());
            }
            else
            {
                sb.AppendLine("pos=none");
                sb.AppendLine("depth=none");
                sb.AppendLine("biome=none");
                sb.AppendLine("batch=none");
            }
            string tmp = statusPath + ".tmp";
            File.WriteAllText(tmp, sb.ToString());
            if (File.Exists(statusPath)) File.Replace(tmp, statusPath, null);
            else File.Move(tmp, statusPath);
        }

        // ---- command channel ----------------------------------------------
        void PollCommands()
        {
            if (!File.Exists(cmdPath)) return;
            string text;
            try { text = File.ReadAllText(cmdPath); File.Delete(cmdPath); }
            catch (IOException) { return; } // writer still has it; retry next poll
            foreach (string raw in text.Split('\n'))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                string[] parts = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                string id = parts[0];
                if (parts.Length < 2) { Out(id, "ERR missing verb"); continue; }
                if (!done.Add(id)) { Out(id, "ERR duplicate id ignored"); continue; }
                string verb = parts[1].ToLowerInvariant();
                string[] args = new string[parts.Length - 2];
                Array.Copy(parts, 2, args, 0, args.Length);
                pendingId = id;
                try { string res = Run(verb, args); if (res != null) Out(id, res); }
                catch (Exception e) { Out(id, "ERR " + e.GetType().Name + ": " + e.Message); }
            }
        }

        void Out(string id, string result)
        {
            result = result.Replace("\r", "").Replace("\n", " | ");
            if (!(result.StartsWith("OK") || result.StartsWith("ERR"))) result = "OK " + result;
            File.AppendAllText(outPath, id + " " + result + "\n");
        }

        string Run(string verb, string[] a)
        {
            switch (verb)
            {
                case "help":
                    return "OK verbs: capture <name> | hud on|off | waterbiomes <file> | look <yaw> <pitch> | cam | dumpterrain <radius> <file> | help pos biome batch teleport x y z | near <radius> [max] | newgame creative | skipintro | shot <file> | quit";
                case "pos": NeedIngame(); return "OK " + PosStr();
                case "biome": NeedIngame(); return "OK " + BiomeStr();
                case "batch": NeedIngame(); return "OK " + BatchStr();
                case "teleport":
                    {
                        NeedIngame();
                        if (a.Length < 3) return "ERR usage: teleport x y z";
                        var v = new Vector3(Pf(a[0]), Pf(a[1]), Pf(a[2]));
                        Player.main.SetPosition(v);
                        return "OK teleported to " + F(v.x) + " " + F(v.y) + " " + F(v.z);
                    }
                case "near": NeedIngame(); return Near(a);
                case "newgame":
                    {
                        if (a.Length < 1 || a[0].ToLowerInvariant() != "creative") return "ERR usage: newgame creative";
                        if (uGUI_MainMenu.main == null) return "ERR not at the main menu";
                        newGameSession = true;
                        uGUI_MainMenu.main.OnButtonCreative();
                        return "OK newgame creative started (uGUI_MainMenu.OnButtonCreative)";
                    }
                case "skipintro":
                    {
                        // Creative sets GameModeOption.InitialItems, so MainGameController.ShouldPlayIntro() is false and the game
                        // already calls EscapePod.StopIntroCinematic(true) itself; this verb repeats that call on demand.
                        NeedIngame();
                        if (EscapePod.main == null) return "ERR no EscapePod";
                        EscapePod.main.StopIntroCinematic(true);
                        return "OK EscapePod.StopIntroCinematic(true) called";
                    }
                case "shot":
                    {
                        string name = a.Length > 0 ? Path.GetFileName(a[0]) : "shot_" + Time.frameCount + ".png";
                        if (!name.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) name += ".png";
                        string path = Path.Combine(io, name);
                        ScreenCapture.CaptureScreenshot(path);
                        return "OK screenshot requested " + name + " (written at end of frame)";
                    }
                case "look":
                    {
                        NeedIngame();
                        if (a.Length < 2) return "ERR usage: look <yaw_deg> <pitch_deg>";
                        StartCoroutine(LookCo(pendingId, Pf(a[0]), Mathf.Clamp(Pf(a[1]), -89f, 89f)));
                        return null;
                    }
                case "cam": NeedIngame(); return CamInfo();
                case "chunkinfo": NeedIngame(); return ChunkInfo();
                case "dumpterrain": NeedIngame(); return DumpTerrain(a);
                case "waterbiomes": NeedIngame(); return WaterBiomes(a);
                case "hud":
                    {
                        // hud off = HideForScreenshots.Hide(Mask|HUD|ViewModel) (helmet mask, HUD, arms/tool); hud on = Hide(None) restores all.
                        if (a.Length < 1) return "ERR usage: hud on|off";
                        bool off = a[0].ToLowerInvariant() == "off";
                        HideForScreenshots.Hide(off ? (HideForScreenshots.HideType.Mask | HideForScreenshots.HideType.HUD | HideForScreenshots.HideType.ViewModel) : HideForScreenshots.HideType.None);
                        return "OK hud " + (off ? "hidden" : "shown");
                    }
                case "capture":
                    {
                        // capture <name>: hide HUD, write <name>.json (camera pose, fov, biome, water settings at the camera), screenshot <name>.png, restore HUD.
                        NeedIngame();
                        string name = a.Length > 0 ? Path.GetFileNameWithoutExtension(a[0]) : "capture_" + DateTime.Now.ToString("yyyyMMdd_HHmmss", IC);
                        StartCoroutine(CaptureCo(pendingId, name));
                        return null;
                    }
                case "quit":
                    Out_Quit();
                    return "OK quitting (Application.Quit, no save)";
                default: return "ERR unknown verb " + verb;
            }
        }

        // look: SN1 stores look as MainCameraControl.rotationX (yaw, local to the camera's parent) and rotationY (pitch, + = up,
        // clamped to minimumY/maximumY = +-80 by default); OnUpdate re-applies them every frame from these fields. We widen the clamp
        // to +-89, set the fields, wait frames, then correct rotationX by the measured world-yaw error (parent may be rotated).
        System.Collections.IEnumerator LookCo(string id, float yaw, float pitch)
        {
            var mcc = MainCameraControl.main;
            Camera cam = Camera.main;
            if (mcc == null || cam == null) { Out(id, "ERR no MainCameraControl/camera"); yield break; }
            mcc.minimumY = -89f; mcc.maximumY = 89f;
            mcc.rotationX = yaw; mcc.rotationY = pitch;
            for (int i = 0; i < 3; i++) yield return null;
            for (int iter = 0; iter < 3; iter++)
            {
                float cy = cam.transform.eulerAngles.y;
                float err = Mathf.DeltaAngle(cy, yaw);
                if (Mathf.Abs(err) < 0.3f) break;
                mcc.rotationX += err;
                for (int i = 0; i < 3; i++) yield return null;
            }
            Vector3 e = cam.transform.eulerAngles;
            float rp = e.x > 180f ? e.x - 360f : e.x;
            Out(id, "OK yaw=" + F(e.y) + " pitch=" + F(-rp) + " (requested " + F(yaw) + " " + F(pitch) + "; pitch reported + = up; euler.x=" + F(rp) + ")");
        }

        string CamInfo()
        {
            Camera c = Camera.main;
            if (c == null) return "ERR no Camera.main";
            Vector3 p = c.transform.position, e = c.transform.eulerAngles;
            float vf = c.fieldOfView;
            float hf = 2f * Mathf.Atan(Mathf.Tan(vf * Mathf.Deg2Rad * 0.5f) * c.aspect) * Mathf.Rad2Deg;
            return "OK pos=" + F(p.x) + "," + F(p.y) + "," + F(p.z) + " euler=" + F(e.x) + "," + F(e.y) + "," + F(e.z)
                + " fovV=" + F(vf) + " fovH=" + F(hf) + " aspect=" + c.aspect.ToString("0.0000", IC)
                + " screen=" + Screen.width + "x" + Screen.height + " pixel=" + c.pixelWidth + "x" + c.pixelHeight
                + " near=" + F(c.nearClipPlane) + " far=" + F(c.farClipPlane) + " cam=" + c.name
                + " player=" + F(Player.main.transform.position.x) + "," + F(Player.main.transform.position.y) + "," + F(Player.main.transform.position.z);
        }

        // dumpterrain <radius_m> <file>: file is a bare name (written into the io folder) or a full path (parent folder is created).
        string DumpTerrain(string[] a)
        {
            if (a.Length < 2) return "ERR usage: dumpterrain <radius_m> <file>";
            float r = Pf(a[0]);
            string path = Path.IsPathRooted(a[1]) ? a[1] : Path.Combine(io, Path.GetFileName(a[1]));
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            Vector3 pp = Player.main.transform.position;
            int colls = 0, tris = 0, unreadable = 0, skipped = 0; long verts = 0;
            var sb = new StringBuilder();
            sb.AppendLine("# SN1 terrain collider dump, Unity world space (metres, +Y up, +Z north). Player " + F(pp.x) + " " + F(pp.y) + " " + F(pp.z) + " radius " + F(r));
            int vbase = 0;
            foreach (MeshCollider mc in UnityEngine.Object.FindObjectsOfType<MeshCollider>())
            {
                if (mc == null || !mc.enabled || !mc.gameObject.activeInHierarchy || !mc.name.StartsWith("ChunkCollider")) { skipped++; continue; }
                if (mc.bounds.SqrDistance(pp) > r * r) continue;
                Mesh m = mc.sharedMesh;
                if (m == null) { skipped++; continue; }
                if (!m.isReadable) { unreadable++; continue; }
                Vector3[] vs = m.vertices; int[] ts = m.triangles;
                Vector3 wp = mc.transform.position;
                sb.AppendLine("o ChunkCollider_" + F(wp.x) + "_" + F(wp.y) + "_" + F(wp.z));
                foreach (Vector3 v in vs) { Vector3 w = mc.transform.TransformPoint(v); sb.AppendLine("v " + w.x.ToString("0.###", IC) + " " + w.y.ToString("0.###", IC) + " " + w.z.ToString("0.###", IC)); }
                for (int i = 0; i + 2 < ts.Length; i += 3)
                    sb.AppendLine("f " + (vbase + ts[i] + 1) + " " + (vbase + ts[i + 1] + 1) + " " + (vbase + ts[i + 2] + 1));
                vbase += vs.Length; verts += vs.Length; tris += ts.Length / 3; colls++;
            }
            string NL = Environment.NewLine;
            string extra = "";
            if (tris == 0)
            {
                // ChunkCollider meshes carry no CPU vertex data (sharedMesh.vertexCount == 0; the physics mesh is baked, then cleared).
                // Fallback 1: terrain render pieces (TerrainChunkPiece.Mesh()) when readable. Fallback 2: raycast the terrain layer (30).
                int rp = 0, rpReadable = 0, rv = 0, rt = 0; var rsb = new StringBuilder(); int rbase = 0;
                rsb.AppendLine("# SN1 terrain render-piece meshes, Unity world space");
                foreach (TerrainChunkPiece pc in UnityEngine.Object.FindObjectsOfType<TerrainChunkPiece>())
                {
                    if (pc == null || pc is TerrainChunkPieceCollider) continue;
                    Mesh m = pc.Mesh(); if (m == null || m.vertexCount == 0) continue; rp++;
                    if (!m.isReadable) continue;
                    MeshRenderer mr = pc.meshRenderer; if (mr != null && mr.bounds.SqrDistance(pp) > r * r) continue;
                    rpReadable++;
                    Vector3[] vs = m.vertices; int[] ts = m.triangles; Transform t = pc.transform;
                    rsb.AppendLine("o Render_" + F(t.position.x) + "_" + F(t.position.y) + "_" + F(t.position.z));
                    foreach (Vector3 v in vs) { Vector3 w = t.TransformPoint(v); rsb.AppendLine("v " + w.x.ToString("0.###", IC) + " " + w.y.ToString("0.###", IC) + " " + w.z.ToString("0.###", IC)); }
                    for (int i = 0; i + 2 < ts.Length; i += 3) rsb.AppendLine("f " + (rbase + ts[i] + 1) + " " + (rbase + ts[i + 1] + 1) + " " + (rbase + ts[i + 2] + 1));
                    rbase += vs.Length; rv += vs.Length; rt += ts.Length / 3;
                }
                if (rt > 0) File.WriteAllText(Path.ChangeExtension(path, null) + "_render.obj", rsb.ToString());
                extra += " renderPieces=" + rp + " renderReadable=" + rpReadable + " renderTris=" + rt;
                // Raycast heightfield: step 2 m on XZ, RaycastAll down from p.y+r and up from p.y-r against layer 30 (terrain).
                const float step = 2f; int mask = 1 << 30;
                int n = (int)(2f * r / step) + 1; int down = 0, up = 0, rtri = 0;
                var rs = new StringBuilder();
                rs.AppendLine("# SN1 terrain surface by raycast on layer 30, step " + F(step) + " m. o heightfield = first hit from above, triangulated where neighbours differ < 1.5 m; o points_down_extra / points_up = further hits (point cloud)");
                int[,] idx = new int[n, n]; float[,] hy = new float[n, n]; int vi = 0;
                var extraDown = new StringBuilder(); var upPts = new StringBuilder();
                rs.AppendLine("o heightfield");
                var hf = new StringBuilder();
                for (int ix = 0; ix < n; ix++) for (int iz = 0; iz < n; iz++)
                {
                    float x = pp.x - r + ix * step, z = pp.z - r + iz * step; idx[ix, iz] = 0;
                    if ((x - pp.x) * (x - pp.x) + (z - pp.z) * (z - pp.z) > r * r) continue;
                    RaycastHit[] hs = Physics.RaycastAll(new Vector3(x, pp.y + r, z), Vector3.down, 2f * r, mask, QueryTriggerInteraction.Ignore);
                    Array.Sort(hs, (a2, b2) => b2.point.y.CompareTo(a2.point.y));
                    for (int k = 0; k < hs.Length; k++)
                    {
                        Vector3 h = hs[k].point; down++;
                        string line = "v " + h.x.ToString("0.###", IC) + " " + h.y.ToString("0.###", IC) + " " + h.z.ToString("0.###", IC);
                        if (k == 0) { hf.AppendLine(line); vi++; idx[ix, iz] = vi; hy[ix, iz] = h.y; }
                        else extraDown.AppendLine(line);
                    }
                    RaycastHit[] us = Physics.RaycastAll(new Vector3(x, pp.y - r, z), Vector3.up, 2f * r, mask, QueryTriggerInteraction.Ignore);
                    foreach (RaycastHit h2 in us) { up++; upPts.AppendLine("v " + h2.point.x.ToString("0.###", IC) + " " + h2.point.y.ToString("0.###", IC) + " " + h2.point.z.ToString("0.###", IC)); }
                }
                rs.Append(hf.ToString());
                for (int ix = 0; ix + 1 < n; ix++) for (int iz = 0; iz + 1 < n; iz++)
                {
                    int a0 = idx[ix, iz], b0 = idx[ix + 1, iz], c0 = idx[ix, iz + 1], d0 = idx[ix + 1, iz + 1];
                    if (a0 > 0 && b0 > 0 && c0 > 0 && Mathf.Abs(hy[ix, iz] - hy[ix + 1, iz]) < 1.5f && Mathf.Abs(hy[ix, iz] - hy[ix, iz + 1]) < 1.5f) { rs.AppendLine("f " + a0 + " " + c0 + " " + b0); rtri++; }
                    if (b0 > 0 && c0 > 0 && d0 > 0 && Mathf.Abs(hy[ix + 1, iz + 1] - hy[ix + 1, iz]) < 1.5f && Mathf.Abs(hy[ix + 1, iz + 1] - hy[ix, iz + 1]) < 1.5f) { rs.AppendLine("f " + b0 + " " + c0 + " " + d0); rtri++; }
                }
                rs.AppendLine("o points_down_extra"); rs.Append(extraDown.ToString());
                rs.AppendLine("o points_up"); rs.Append(upPts.ToString());
                File.WriteAllText(path, rs.ToString());
                extra += " rayDownHits=" + down + " rayUpHits=" + up + " heightfieldVerts=" + vi + " heightfieldTris=" + rtri + " (main file = raycast surface)";
                tris = rtri; verts = vi;
            }
            else File.WriteAllText(path, sb.ToString());
            File.WriteAllText(Path.ChangeExtension(path, ".txt"), "player_pos=" + F(pp.x) + " " + F(pp.y) + " " + F(pp.z) + NL + "radius=" + F(r) + NL + "colliders=" + colls + NL + "triangles=" + tris + NL + "vertices=" + verts + NL + "unreadable_meshes=" + unreadable + NL + "info=" + extra + NL + "utc=" + DateTime.UtcNow.ToString("o", IC) + NL);
            return "OK colliders=" + colls + " triangles=" + tris + " vertices=" + verts + " unreadable=" + unreadable + " nonchunk_or_inactive_skipped=" + skipped + " file=" + path + extra;
        }

        // chunkinfo: diagnostics for the 3 nearest ChunkCollider objects (components, mesh data availability)
        string ChunkInfo()
        {
            Vector3 pp = Player.main.transform.position;
            var list = new List<MeshCollider>();
            foreach (MeshCollider mc in UnityEngine.Object.FindObjectsOfType<MeshCollider>())
                if (mc != null && mc.name.StartsWith("ChunkCollider")) list.Add(mc);
            list.Sort((x, y) => x.bounds.SqrDistance(pp).CompareTo(y.bounds.SqrDistance(pp)));
            var sb = new StringBuilder("OK chunkColliders=" + list.Count + ": ");
            for (int i = 0; i < 3 && i < list.Count; i++)
            {
                MeshCollider mc = list[i]; Mesh m = mc.sharedMesh;
                sb.Append("[" + mc.name + " pos=" + F(mc.transform.position.x) + "," + F(mc.transform.position.y) + "," + F(mc.transform.position.z) + " scale=" + mc.transform.lossyScale + " parent=" + (mc.transform.parent != null ? mc.transform.parent.name : "-") + " layer=" + mc.gameObject.layer + " convex=" + mc.convex + " boundsSize=" + mc.bounds.size + " comps=");
                foreach (Component c in mc.GetComponents<Component>()) sb.Append(c.GetType().Name + ",");
                sb.Append(" parentComps=");
                if (mc.transform.parent != null) foreach (Component c in mc.transform.parent.GetComponents<Component>()) sb.Append(c.GetType().Name + ",");
                sb.Append(" sharedMesh=" + (m == null ? "null" : m.name + " vc=" + m.vertexCount + " sub=" + m.subMeshCount + " readable=" + m.isReadable + " vertsLen=" + m.vertices.Length + " idxLen=" + m.triangles.Length));
                var mf = mc.GetComponentInChildren<MeshFilter>(); sb.Append(" meshFilter=" + (mf == null || mf.sharedMesh == null ? "none" : mf.sharedMesh.name + " vc=" + mf.sharedMesh.vertexCount));
                sb.Append("] ");
            }
            return sb.ToString();
        }


        // ---- water / biome look --------------------------------------------
        static string J(string v) { return "\"" + (v ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\""; }
        static string Jf(float v) { return v.ToString("R", IC); }
        static string Jv(Vector3 v) { return "[" + Jf(v.x) + "," + Jf(v.y) + "," + Jf(v.z) + "]"; }
        static string Jc(Color c) { return "[" + Jf(c.r) + "," + Jf(c.g) + "," + Jf(c.b) + "," + Jf(c.a) + "]"; }

        static string SettingsJson(WaterscapeVolume.Settings s)
        {
            Vector4 es = s.GetExtinctionAndScatteringCoefficients(); Vector4 em = s.GetEmissive();
            Color sl = s.scatteringColor.linear;
            return "{\"absorption\":" + Jv(s.absorption) + ",\"scattering\":" + Jf(s.scattering) + ",\"scatteringColor\":" + Jc(s.scatteringColor)
                + ",\"murkiness\":" + Jf(s.murkiness) + ",\"emissive\":" + Jc(s.emissive) + ",\"emissiveScale\":" + Jf(s.emissiveScale)
                + ",\"startDistance\":" + Jf(s.startDistance) + ",\"sunlightScale\":" + Jf(s.sunlightScale) + ",\"ambientScale\":" + Jf(s.ambientScale)
                + ",\"temperature\":" + Jf(s.temperature)
                + ",\"derived_extinction_per_m\":" + Jv(new Vector3(es.x, es.y, es.z)) + ",\"derived_scattering_per_m\":" + Jf(es.w)
                + ",\"derived_scattering_rgb_per_m\":" + Jv(new Vector3(sl.r * es.w, sl.g * es.w, sl.b * es.w))
                + ",\"derived_emissive\":" + Jv(new Vector3(em.x, em.y, em.z)) + "}";
        }

        // Public simple-typed fields of a component, by reflection (global water/sky scalars not mapped by name yet).
        static string FieldsJson(object o)
        {
            if (o == null) return "null";
            var sb = new StringBuilder("{");
            bool first = true;
            foreach (var f in o.GetType().GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
            {
                object v; try { v = f.GetValue(o); } catch { continue; }
                string js;
                if (v is float) js = Jf((float)v);
                else if (v is int || v is bool) js = v.ToString().ToLowerInvariant();
                else if (v is Vector3) js = Jv((Vector3)v);
                else if (v is Color) js = Jc((Color)v);
                else if (v is string || (v != null && v.GetType().IsEnum)) js = J(v.ToString());
                else continue;
                sb.Append((first ? "" : ",") + J(f.Name) + ":" + js); first = false;
            }
            return sb.Append("}").ToString();
        }

        static string ColliderJson(Collider c)
        {
            if (c == null) return "null";
            Transform t = c.transform;
            string sh = "{\"type\":" + J(c.GetType().Name) + ",\"enabled\":" + c.enabled.ToString().ToLowerInvariant()
                + ",\"pos\":" + Jv(t.position) + ",\"euler\":" + Jv(t.eulerAngles) + ",\"lossyScale\":" + Jv(t.lossyScale)
                + ",\"boundsMin\":" + Jv(c.bounds.min) + ",\"boundsMax\":" + Jv(c.bounds.max);
            var b = c as BoxCollider; if (b != null) sh += ",\"center\":" + Jv(b.center) + ",\"size\":" + Jv(b.size);
            var s = c as SphereCollider; if (s != null) sh += ",\"center\":" + Jv(s.center) + ",\"radius\":" + Jf(s.radius);
            var cp = c as CapsuleCollider; if (cp != null) sh += ",\"center\":" + Jv(cp.center) + ",\"radius\":" + Jf(cp.radius) + ",\"height\":" + Jf(cp.height) + ",\"direction\":" + cp.direction;
            var m = c as MeshCollider; if (m != null) sh += ",\"mesh\":" + J(m.sharedMesh != null ? m.sharedMesh.name : "null");
            return sh + "}";
        }

        // waterbiomes <file>: every WaterBiomeManager.biomeSettings entry, the loaded AtmosphereVolumes (streamed: only those near the
        // player exist), the global WaterscapeVolume scalars, and the biome + settings at the camera. JSON.
        string WaterBiomes(string[] a)
        {
            if (a.Length < 1) return "ERR usage: waterbiomes <file>";
            string path = Path.IsPathRooted(a[0]) ? a[0] : Path.Combine(io, Path.GetFileName(a[0]));
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var wbm = WaterBiomeManager.main;
            if (wbm == null) return "ERR no WaterBiomeManager.main";
            var sb = new StringBuilder("{\n");
            sb.Append("\"utc\":" + J(DateTime.UtcNow.ToString("o", IC)) + ",\n\"camera\":" + CameraJson() + ",\n");
            sb.Append("\"biomeSettings\":[\n");
            for (int i = 0; i < wbm.biomeSettings.Count; i++)
            {
                var bs = wbm.biomeSettings[i];
                sb.Append((i > 0 ? ",\n" : "") + "{\"index\":" + i + ",\"name\":" + J(bs.name) + ",\"sky\":" + J(bs.skyPrefab != null ? bs.skyPrefab.name : null) + ",\"settings\":" + SettingsJson(bs.settings) + "}");
            }
            sb.Append("\n],\n\"atmosphereVolumes\":[\n");
            int nv = 0;
            var ad = AtmosphereDirector.main;
            if (ad != null && ad.GetVolumes() != null)
                foreach (AtmosphereVolume v in ad.GetVolumes())
                {
                    if (v == null) continue;
                    sb.Append((nv++ > 0 ? ",\n" : "") + "{\"name\":" + J(v.name) + ",\"overrideBiome\":" + J(v.overrideBiome) + ",\"priority\":" + v.priority
                        + ",\"highDetail\":" + v.highDetail.ToString().ToLowerInvariant() + ",\"affectsVisuals\":" + v.affectsVisuals.ToString().ToLowerInvariant()
                        + ",\"fogColor\":" + Jc(v.fogColor) + ",\"fogStart\":" + Jf(v.fogStartDistance) + ",\"fogMax\":" + Jf(v.fogMaxDistance)
                        + ",\"collider\":" + ColliderJson(v.GetComponent<Collider>()) + "}");
                }
            sb.Append("\n],\n");
            var wv = UnityEngine.Object.FindObjectOfType<WaterscapeVolume>();
            sb.Append("\"waterscapeVolume\":" + FieldsJson(wv) + "\n}\n");
            File.WriteAllText(path, sb.ToString());
            return "OK biomeSettings=" + wbm.biomeSettings.Count + " atmosphereVolumes=" + nv + " file=" + path;
        }

        string CameraJson()
        {
            Camera c = Camera.main; var p = Player.main;
            if (c == null) return "null";
            Vector3 cp = c.transform.position, e = c.transform.eulerAngles;
            float pitch = e.x > 180f ? 360f - e.x : -e.x; // + = up
            float hf = 2f * Mathf.Atan(Mathf.Tan(c.fieldOfView * Mathf.Deg2Rad * 0.5f) * c.aspect) * Mathf.Rad2Deg;
            string biome = "", biomeVis = "";
            WaterscapeVolume.Settings s = null; bool found = false;
            var wbm = WaterBiomeManager.main;
            if (wbm != null) { biome = wbm.GetBiome(cp, false); biomeVis = wbm.GetBiome(cp, true); found = wbm.GetSettings(cp, true, out s); }
            return "{\"pos\":" + Jv(cp) + ",\"euler\":" + Jv(e) + ",\"yaw\":" + Jf(e.y) + ",\"pitch_up\":" + Jf(pitch) + ",\"roll\":" + Jf(e.z)
                + ",\"fovV\":" + Jf(c.fieldOfView) + ",\"fovH\":" + Jf(hf) + ",\"aspect\":" + Jf(c.aspect) + ",\"screen\":[" + Screen.width + "," + Screen.height + "]"
                + ",\"player\":" + (p != null ? Jv(p.transform.position) : "null") + ",\"depth\":" + (p != null ? Jf(p.GetDepth()) : "null")
                + ",\"playerBiome\":" + J(p != null ? p.GetBiomeString() : null) + ",\"biome\":" + J(biome) + ",\"biomeVisual\":" + J(biomeVis)
                + ",\"settingsFound\":" + found.ToString().ToLowerInvariant() + ",\"settings\":" + (s != null ? SettingsJson(s) : "null")
                + ",\"dayScalar\":" + (DayNightCycle.main != null ? Jf(DayNightCycle.main.GetDayScalar()) : "null") + "}";
        }

        // capture <name>: HUD/mask/arms hidden for the shot, then restored. Files land in the io folder.
        System.Collections.IEnumerator CaptureCo(string id, string name)
        {
            HideForScreenshots.Hide(HideForScreenshots.HideType.Mask | HideForScreenshots.HideType.HUD | HideForScreenshots.HideType.ViewModel);
            for (int i = 0; i < 3; i++) yield return null;
            string png = Path.Combine(io, name + ".png"), meta = Path.Combine(io, name + ".json");
            string cj = null;
            try { cj = CameraJson(); File.WriteAllText(meta, "{\"name\":" + J(name) + ",\"utc\":" + J(DateTime.UtcNow.ToString("o", IC)) + ",\"camera\":" + cj + "}\n"); }
            catch (Exception e) { Out(id, "ERR meta: " + e.Message); }
            ScreenCapture.CaptureScreenshot(png);
            for (int i = 0; i < 5; i++) yield return null;
            yield return new WaitForEndOfFrame();
            HideForScreenshots.Hide(HideForScreenshots.HideType.None);
            Out(id, "OK captured " + name + ".png + " + name + ".json " + (cj ?? ""));
        }

        void Out_Quit() { Logger.LogInfo("quit command: Application.Quit()"); Application.Quit(); }

        void NeedIngame() { if (GameState() != "ingame") throw new InvalidOperationException("not ingame (state=" + GameState() + ")"); }
        static float Pf(string s) { return float.Parse(s, IC); }

        string Near(string[] a)
        {
            float radius = a.Length > 0 ? Pf(a[0]) : 20f;
            int max = a.Length > 1 ? int.Parse(a[1], IC) : 20;
            radius = Mathf.Clamp(radius, 0.5f, 500f);
            max = Mathf.Clamp(max, 1, 200);
            Vector3 p = Player.main.transform.position;
            Collider[] cols = Physics.OverlapSphere(p, radius, ~0, QueryTriggerInteraction.Ignore);
            var seen = new Dictionary<GameObject, float>();
            foreach (Collider c in cols)
            {
                if (c == null) continue;
                GameObject root = RootOf(c);
                if (root == null || seen.ContainsKey(root)) continue;
                seen[root] = Vector3.Distance(p, root.transform.position);
            }
            var list = new List<KeyValuePair<GameObject, float>>(seen);
            list.Sort((x, y) => x.Value.CompareTo(y.Value));
            var sb = new StringBuilder();
            sb.Append("OK " + list.Count + " objects within " + F(radius) + " m (colliders " + cols.Length + "), showing " + Math.Min(max, list.Count) + ": ");
            for (int i = 0; i < list.Count && i < max; i++)
            {
                GameObject go = list[i].Key;
                Vector3 q = go.transform.position;
                string cid = "-";
                var pi = go.GetComponent<PrefabIdentifier>();
                if (pi != null) cid = pi.ClassId;
                sb.Append("[" + go.name + " pos=" + F(q.x) + "," + F(q.y) + "," + F(q.z) + " d=" + F(list[i].Value) + " classId=" + cid + "] ");
            }
            return sb.ToString();
        }

        static GameObject RootOf(Collider c)
        {
            var pi = c.GetComponentInParent<PrefabIdentifier>();
            if (pi != null) return pi.gameObject;
            if (c.attachedRigidbody != null) return c.attachedRigidbody.gameObject;
            return c.gameObject;
        }
    }
}
