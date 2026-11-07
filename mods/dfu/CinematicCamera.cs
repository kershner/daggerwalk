using System;
using System.Collections.Generic;
using System.Reflection;
using System.IO;
using UnityEngine;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.UserInterface;
using DaggerfallWorkshop.Game.Utility.ModSupport;
using DaggerfallWorkshop.Game.Utility.ModSupport.ModSettings;
using Shot = DaggerwalkCameraShot;

// The director follows the No Man's Walk implementation. Only the adapter below
// knows about DFU: gameplay owns the camera between render passes.
[Serializable]
public class CinematicCameraSettings
{
    public float maximum_shot_seconds = 39.61f;
    public float distance_max = 60.32f;
    public float height_max = 40.41f;
    public float speed_max = 3f;
    public float zoom_max = 4f;
    public bool smooth_transitions = false;
    public float transition_seconds = 3f;
    public bool hold_shot = false;
    public float vertical_response = 2f;

    public static CinematicCameraSettings Read(ModSettings source)
    {
        var value = new CinematicCameraSettings();
        value.maximum_shot_seconds = source.GetFloat("Camera", "MaximumShotSeconds");
        value.distance_max = source.GetFloat("Camera", "MaximumDistance");
        value.height_max = source.GetFloat("Camera", "MaximumHeight");
        value.speed_max = source.GetFloat("Camera", "MaximumOrbitSpeed");
        value.zoom_max = source.GetFloat("Camera", "MaximumDistanceMultiplier");
        value.hold_shot = source.GetBool("Camera", "HoldShot");
        value.vertical_response = source.GetFloat("Camera", "VerticalResponse");
        value.smooth_transitions = source.GetBool("Transitions", "SmoothTransitions");
        value.transition_seconds = source.GetFloat("Transitions", "TransitionSeconds");
        value.Normalize();
        return value;
    }

    private static float Limit(float value, float fallback, float min, float max)
    {
        return float.IsNaN(value) || float.IsInfinity(value) ? fallback : Mathf.Clamp(value, min, max);
    }

    public void Normalize()
    {
        maximum_shot_seconds = Limit(maximum_shot_seconds, 39.61f, 10, 120);
        distance_max = Limit(distance_max, 60.32f, 3, 120);
        height_max = Limit(height_max, 40.41f, 1.5f, 80);
        speed_max = Limit(speed_max, 3, 2.291831f, 20);
        zoom_max = Limit(zoom_max, 4, 1, 4);
        transition_seconds = Limit(transition_seconds, 3, 0, 15);
        vertical_response = Limit(vertical_response, 2, 0.1f, 20);
    }
}

// Keep the enum top-level. DFU 1.1.1's in-memory compiler emits invalid enum
// metadata when this is nested in the director, although Unity's compiler works.
public enum DaggerwalkCameraShot : int { Rear, Side, Front, HighOrbit }

public sealed class DaggerwalkCameraDirector
{
    private readonly System.Random rng;
    private readonly List<Shot> bag = new List<Shot>();
    private bool initialized;
    private bool forceNext;
    private float remaining, elapsed, transitionElapsed;
    private float distance, height, scale, orbitSpeed, side;
    private Vector3 heading, anchor, previousPlayer, offset, transitionFrom;
    private bool hasTransition;
    public Shot CurrentShot { get; private set; }
    public Vector3 Position { get; private set; }
    public Vector3 Target { get; private set; }
    public bool Cut { get; private set; }

    public DaggerwalkCameraDirector(int seed) { rng = new System.Random(seed); }
    private float Range(float low, float high) { return low + (float)rng.NextDouble() * (high - low); }
    private static float Response(float speed, float dt) { return 1f - (float)Math.Exp(-speed * dt); }

    public void Reset()
    {
        initialized = false;
        forceNext = false;
        bag.Clear();
    }

    public void Next() { forceNext = true; }

    // Polar interpolation prevents opposite shots travelling through the player.
    public static Vector3 BlendOffset(Vector3 a, Vector3 b, float t)
    {
        float ar = (float)Math.Sqrt(a.x * a.x + a.z * a.z);
        float br = (float)Math.Sqrt(b.x * b.x + b.z * b.z);
        float start = (float)Math.Atan2(a.x, a.z);
        float end = (float)Math.Atan2(b.x, b.z);
        float delta = (float)Math.Atan2(Math.Sin(end - start), Math.Cos(end - start));
        float angle = start + delta * t;
        float radius = ar + (br - ar) * t;
        return new Vector3((float)Math.Sin(angle) * radius, a.y + (b.y - a.y) * t,
            (float)Math.Cos(angle) * radius);
    }

    public void Update(float dt, Vector3 feet, Vector3 forward, CinematicCameraSettings settings)
    {
        if (float.IsNaN(dt) || float.IsInfinity(dt) || dt <= 0 || dt > 0.25f)
            throw new ArgumentOutOfRangeException("dt");
        // Teleports and DFU floating-origin shifts start afresh, never fly across the world.
        if (initialized && (feet - previousPlayer).sqrMagnitude > 1600f) Reset();
        previousPlayer = feet;
        bool first = !initialized;
        if (first) anchor = feet;
        else
        {
            Vector3 delta = feet - anchor;
            float horizontal = Response(4f, dt);
            anchor += new Vector3(delta.x * horizontal, delta.y * Response(settings.vertical_response, dt), delta.z * horizontal);
        }
        Cut = first || forceNext || (remaining <= 0 && !settings.hold_shot);
        if (Cut)
        {
            hasTransition = !first;
            transitionFrom = offset;
            transitionElapsed = 0;
            forceNext = false;
            if (bag.Count == 0)
            {
                bag.AddRange(new[] { Shot.Rear, Shot.Side, Shot.Front, Shot.HighOrbit });
                for (int i = bag.Count - 1; i > 0; i--)
                {
                    int j = rng.Next(i + 1);
                    Shot swap = bag[i]; bag[i] = bag[j]; bag[j] = swap;
                }
                if (!first && bag[3] == CurrentShot)
                {
                    Shot swap = bag[0]; bag[0] = bag[3]; bag[3] = swap;
                }
            }
            CurrentShot = bag[bag.Count - 1];
            bag.RemoveAt(bag.Count - 1);
            forward.y = 0;
            heading = forward.sqrMagnitude > 0.0001f ? forward.normalized : Vector3.forward;
            remaining = Range(10, settings.maximum_shot_seconds);
            elapsed = 0;
            side = rng.Next(2) == 0 ? -1 : 1;
            distance = Range(3, settings.distance_max);
            height = Range(1.5f, settings.height_max);
            scale = Range(1, settings.zoom_max);
            // Keep distant orbits below 6 metres/second to limit terrain churn.
            float cap = Math.Min(settings.speed_max, (float)(6 / (distance * scale) * 180 / Math.PI));
            orbitSpeed = Range(Math.Min(2.291831f, cap), cap);
            initialized = true;
        }
        remaining = Math.Min(remaining, settings.maximum_shot_seconds) - dt;
        elapsed += dt;
        transitionElapsed += dt;
        Vector3 right = new Vector3(heading.z, 0, -heading.x);
        float radius = distance * scale;
        Vector3 desired;
        switch (CurrentShot)
        {
            case Shot.Rear: desired = -heading * radius; break;
            case Shot.Front: desired = heading * radius; break;
            case Shot.Side:
                desired = right * (side * radius) - heading * (Math.Min(4, distance * 0.2f) * scale);
                break;
            default:
                float angle = side * (0.6f + elapsed * orbitSpeed * (float)(Math.PI / 180));
                desired = -heading * (radius * (float)Math.Cos(angle)) + right * (radius * (float)Math.Sin(angle));
                break;
        }
        desired.y = height;
        if (hasTransition && settings.smooth_transitions && transitionElapsed < settings.transition_seconds)
        {
            float t = transitionElapsed / settings.transition_seconds;
            desired = BlendOffset(transitionFrom, desired, t * t * t * (10 - 15 * t + 6 * t * t));
        }
        offset = desired;
        Position = anchor + offset;
        Target = anchor + Vector3.up * 1.4f;
    }
}

// Optional adapter for the installed Eye Of The Beholder 2.0 PlayerBillboard.
// Keep this in the same source asset so normal DFU source-mod packaging works.
public sealed class DaggerwalkEyeBillboard
{
    private const BindingFlags Members = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    private FieldInfo instanceField, facingField, cameraPositionField, angleField;
    private FieldInfo orientationField, frameField, statesField, firstPersonField;
    private MethodInfo updateBillboard;
    private float nextProbe;
    private bool failed, active;
    private Component billboard;
    private Transform sprite;
    private Mesh mesh;
    private Material material;
    private Vector3 savedPosition, savedScale;
    private Quaternion savedRotation;
    private Texture savedTexture;
    private object savedCameraPosition, savedAngle, savedOrientation, savedFrame, savedFirstPerson;
    private readonly List<Vector2> savedUVs = new List<Vector2>(4);
    private readonly object[] arguments = new object[3];

    public bool Bind(Type type)
    {
        if (type == null || type.FullName != "PlayerBillboard") return false;
        instanceField = type.GetField("Instance", Members);
        facingField = type.GetField("lastMoveDirection", Members);
        cameraPositionField = type.GetField("cameraPosition", Members);
        angleField = type.GetField("currentAngle", Members);
        orientationField = type.GetField("lastOrientation", Members);
        frameField = type.GetField("frameCurrent", Members);
        statesField = type.GetField("stateCurrent", Members);
        firstPersonField = type.GetField("FP", Members);
        updateBillboard = type.GetMethod("UpdateBillboard", Members);
        return instanceField != null && instanceField.IsStatic && facingField != null && facingField.FieldType == typeof(Vector3) &&
            cameraPositionField != null && cameraPositionField.FieldType == typeof(Vector3) &&
            angleField != null && angleField.FieldType == typeof(float) && orientationField != null && orientationField.FieldType == typeof(int) &&
            frameField != null && frameField.FieldType == typeof(int) && statesField != null && statesField.FieldType.IsArray &&
            firstPersonField != null && firstPersonField.FieldType == typeof(bool) && updateBillboard != null &&
            updateBillboard.ReturnType == typeof(void) && updateBillboard.GetParameters().Length == 3 &&
            updateBillboard.GetParameters()[0].ParameterType == typeof(int) && updateBillboard.GetParameters()[1].ParameterType == typeof(int) &&
            updateBillboard.GetParameters()[2].ParameterType == statesField.FieldType;
    }

    // Same signed-angle and eight-direction indexing used by EOB 2.0. Keep
    // facing independent of the cinematic view, including when the player stops.
    public static float ViewAngle(Vector3 playerToCamera, Vector3 facing)
    {
        if (facing.x * facing.x + facing.z * facing.z < 0.0001f) facing = Vector3.forward;
        float cross = playerToCamera.z * facing.x - playerToCamera.x * facing.z;
        float dot = playerToCamera.x * facing.x + playerToCamera.z * facing.z;
        return (float)(Math.Atan2(cross, dot) * 180 / Math.PI);
    }

    public static int Orientation(float angle)
    {
        int sector = -(int)Math.Round(angle / 45f, MidpointRounding.ToEven);
        return (sector % 8 + 8) % 8;
    }

    private bool FindBillboard()
    {
        if (failed) return false;
        if (updateBillboard != null) return true;
        if (Time.unscaledTime < nextProbe) return false;
        nextProbe = Time.unscaledTime + 1;
        var manager = ModManager.Instance;
        if (manager == null) return false;
        var eye = manager.GetModFromGUID("2942ea8c-dbd4-42af-bdf9-8199d2f4a0aa");
        if (eye == null || !eye.Enabled || !eye.IsReady) return false;
        if (!Bind(eye.GetCompiledType("PlayerBillboard")))
        {
            failed = true;
            updateBillboard = null;
            Debug.LogWarning("[CinematicCamera] Eye of the Beholder's sprite API is incompatible; sprite correction is disabled.");
            return false;
        }
        Debug.Log("[CinematicCamera] Eye of the Beholder sprite perspective adapter ready.");
        return true;
    }

    public void Apply(Vector3 cameraPosition, Vector3 cameraForward, Vector3 playerForward)
    {
        if (active) return;
        try
        {
            if (!FindBillboard()) return;
            billboard = instanceField.GetValue(null) as Component;
            if (billboard == null || !billboard.gameObject.activeInHierarchy) return;
            sprite = billboard.transform;
            if (sprite.parent == null) return;
            var renderer = billboard.GetComponent<MeshRenderer>();
            var filter = billboard.GetComponent<MeshFilter>();
            var states = statesField.GetValue(billboard) as Array;
            if (renderer == null || !renderer.enabled || filter == null || filter.sharedMesh == null || states == null || states.Length != 8) return;
            mesh = filter.sharedMesh;
            material = renderer.material;
            savedPosition = sprite.localPosition;
            savedRotation = sprite.localRotation;
            savedScale = sprite.localScale;
            savedTexture = material.mainTexture;
            savedUVs.Clear();
            mesh.GetUVs(0, savedUVs);
            CapturePerspective(billboard);
            // Arm rollback before invoking EOB, including partial failures.
            active = true;
            Vector3 facing = (Vector3)facingField.GetValue(billboard);
            if (facing.x * facing.x + facing.z * facing.z < 0.0001f) facing = playerForward;
            float angle = ViewAngle(cameraPosition - sprite.parent.position, facing);
            ApplyPerspective(billboard, cameraPosition, angle);
            arguments[0] = savedFrame;
            arguments[1] = Orientation(angle);
            arguments[2] = states;
            // Call only the visual update, never EOB's full LateUpdate (which
            // can start attack animations, footsteps, and direction coroutines).
            updateBillboard.Invoke(billboard, arguments);
            Vector3 towardView = new Vector3(-cameraForward.x, 0, -cameraForward.z);
            if (towardView.sqrMagnitude > 0.0001f) sprite.rotation = Quaternion.LookRotation(towardView, Vector3.up);
        }
        catch (Exception ex)
        {
            Restore();
            failed = true;
            Debug.LogWarning("[CinematicCamera] Sprite perspective correction stopped: " + ex.GetBaseException().Message);
        }
    }

    private void CapturePerspective(object target)
    {
        savedCameraPosition = cameraPositionField.GetValue(target);
        savedAngle = angleField.GetValue(target);
        savedOrientation = orientationField.GetValue(target);
        savedFrame = frameField.GetValue(target);
        savedFirstPerson = firstPersonField.GetValue(target);
    }

    private void ApplyPerspective(object target, Vector3 cameraPosition, float angle)
    {
        // A first-person body is still visible from the cinematic camera. Use
        // EOB's third-person visual rules for this render pass only; never
        // toggle its camera mode or saved settings.
        firstPersonField.SetValue(target, false);
        cameraPositionField.SetValue(target, cameraPosition);
        angleField.SetValue(target, angle);
    }

    private void RestorePerspective(object target)
    {
        firstPersonField.SetValue(target, savedFirstPerson);
        cameraPositionField.SetValue(target, savedCameraPosition);
        angleField.SetValue(target, savedAngle);
        orientationField.SetValue(target, savedOrientation);
        frameField.SetValue(target, savedFrame);
    }

    public void Restore()
    {
        if (!active) return;
        active = false;
        if (billboard != null)
        {
            RestorePerspective(billboard);
        }
        if (sprite != null)
        {
            sprite.localPosition = savedPosition;
            sprite.localRotation = savedRotation;
            sprite.localScale = savedScale;
        }
        if (material != null) material.mainTexture = savedTexture;
        if (mesh != null) mesh.SetUVs(0, savedUVs);
        arguments[0] = arguments[1] = arguments[2] = null;
    }
}

[Serializable]
public sealed class DaggerwalkCinematicRequest
{
    public int protocol;
    public string id, session, action;
    public double timestamp;

    public bool CanApply(string currentSession, double now)
    {
        double age = now - timestamp;
        return protocol == 1 && !string.IsNullOrEmpty(id) && !string.IsNullOrEmpty(session) && session == currentSession &&
            (action == "on" || action == "off") && !double.IsNaN(age) && !double.IsInfinity(age) && age >= -2 && age <= 10;
    }
}

[Serializable]
public sealed class DaggerwalkCinematicStatus
{
    public int protocol = 1;
    public string session, status, last_request_id;
    public bool running, enabled, active;
    public double timestamp;
}

[DisallowMultipleComponent]
public sealed class CinematicCamera : MonoBehaviour
{
    private static Mod mod;
    [SerializeField] private CinematicCameraSettings settings = new CinematicCameraSettings();
    [SerializeField] private KeyCode toggleKey = KeyCode.Keypad1;
    [SerializeField] private KeyCode nextShotKey = KeyCode.Keypad2;
    // Inputs sent by this repository's bot and supervisor. Console typing is
    // excluded because shortcuts are only processed while the HUD is active.
    private static readonly HashSet<KeyCode> BotKeys = new HashSet<KeyCode> {
        KeyCode.Backslash, KeyCode.W, KeyCode.S, KeyCode.A, KeyCode.D,
        KeyCode.Insert, KeyCode.Delete, KeyCode.Home, KeyCode.Space, KeyCode.V,
        KeyCode.F9, KeyCode.F11, KeyCode.BackQuote, KeyCode.Escape, KeyCode.Return,
        KeyCode.K, KeyCode.O, KeyCode.Semicolon, KeyCode.Z, KeyCode.X,
        KeyCode.Equals, KeyCode.Tab, KeyCode.L
    };
    private readonly DaggerwalkCameraDirector director = new DaggerwalkCameraDirector(Environment.TickCount);
    private readonly RaycastHit[] hits = new RaycastHit[64];
    private readonly DaggerwalkEyeBillboard eyeBillboard = new DaggerwalkEyeBillboard();
    private bool requested, ready;
    private Camera mainCamera, overlaidCamera, renderPassCamera;
    private Transform originalParent;
    private Vector3 originalLocalPosition, writtenPosition;
    private Quaternion originalLocalRotation, writtenRotation;
    private Vector3 position;
    private Quaternion rotation;
    private float terrainLift;
    private int overlayFrame = -1;
    private string status = "Off";
    private string controlDirectory, controlSession, lastRequestId;
    private float nextControlPoll, nextHeartbeat, nextControlWarning;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;
        // Reuse a component attached for editor testing instead of creating a
        // second camera controller when the virtual mod is also enabled.
        var camera = UnityEngine.Object.FindObjectOfType<CinematicCamera>();
        if (camera == null)
        {
            var go = new GameObject("Daggerwalk Cinematic Camera");
            UnityEngine.Object.DontDestroyOnLoad(go);
            camera = go.AddComponent<CinematicCamera>();
        }
        mod.MessageReceiver = camera.ReceiveMessage;
        mod.LoadSettingsCallback = camera.LoadSettings;
        if (mod.HasSettings) mod.LoadSettings();
        else Debug.LogWarning("[CinematicCamera] Include modsettings.json in the mod manifest to enable DFU settings. Using defaults.");
        // DFU's existing Mod Options picker includes mods with settings and a
        // LoadSettingsCallback. Do not add a separate pause-dropdown entry.
        mod.IsReady = true;
        camera.InitializeControlBridge();
        Debug.Log("[CinematicCamera] Initialized; in-game settings registered.");
    }

    private void Awake()
    {
        settings.Normalize();
        Debug.Log("[CinematicCamera v1.4.0] Script loaded. Numpad 1 toggle; Numpad 2 next shot. Settings: in-game Mod Options > Cinematic Camera.");
    }

    public static double ControlTimestamp()
    {
        return (DateTime.UtcNow.Ticks - 621355968000000000L) / 10000000.0;
    }

    private void InitializeControlBridge()
    {
        controlDirectory = mod.PersistentDataDirectory;
        controlSession = Guid.NewGuid().ToString("N");
        lastRequestId = null;
        PublishControlStatus(true);
    }

    private void PublishControlStatus(bool running)
    {
        if (string.IsNullOrEmpty(controlDirectory)) return;
        nextHeartbeat = Time.unscaledTime + 1;
        try
        {
            Directory.CreateDirectory(controlDirectory);
            var state = new DaggerwalkCinematicStatus {
                session = controlSession, running = running, enabled = requested, active = ready,
                status = status, last_request_id = lastRequestId, timestamp = ControlTimestamp()
            };
            string destination = Path.Combine(controlDirectory, "cinematic_camera_status.json");
            string temporary = destination + ".tmp";
            File.WriteAllText(temporary, JsonUtility.ToJson(state));
            if (File.Exists(destination)) File.Replace(temporary, destination, null);
            else File.Move(temporary, destination);
        }
        catch (Exception ex) { ControlWarning(ex); }
    }

    private void ControlWarning(Exception error)
    {
        if (Time.unscaledTime < nextControlWarning) return;
        nextControlWarning = Time.unscaledTime + 10;
        Debug.LogWarning("[CinematicCamera] Bot bridge: " + error.Message);
    }

    private void PollControlBridge()
    {
        if (string.IsNullOrEmpty(controlDirectory)) return;
        if (Time.unscaledTime >= nextControlPoll)
        {
            nextControlPoll = Time.unscaledTime + 0.25f;
            try
            {
                string path = Path.Combine(controlDirectory, "cinematic_camera_request.json");
                if (File.Exists(path))
                {
                    var request = JsonUtility.FromJson<DaggerwalkCinematicRequest>(File.ReadAllText(path));
                    if (request != null && request.id != lastRequestId && request.CanApply(controlSession, ControlTimestamp()))
                    {
                        bool desired = request.action == "on";
                        if (requested != desired) SetEnabled(desired);
                        lastRequestId = request.id;
                        PublishControlStatus(true);
                    }
                }
            }
            catch (Exception ex) { ControlWarning(ex); }
        }
        if (Time.unscaledTime >= nextHeartbeat) PublishControlStatus(true);
    }

    private static string ShortcutConflict(KeyCode key)
    {
        if (key == KeyCode.None) return null;
        if (BotKeys.Contains(key)) return "a Daggerwalk bot input";
        var input = InputManager.Instance;
        if (input != null)
            foreach (InputManager.Actions action in Enum.GetValues(typeof(InputManager.Actions)))
                if (input.GetBinding(action, true) == key || input.GetBinding(action, false) == key)
                    return "DFU control " + action;
        // Movement bindings do not include HUD and dialog shortcuts (such as
        // F10's LargeHUDToggle). Check those separately, including overrides.
        foreach (DaggerfallShortcut.Buttons button in Enum.GetValues(typeof(DaggerfallShortcut.Buttons)))
            if (button != DaggerfallShortcut.Buttons.None && DaggerfallShortcut.GetBinding(button).IsSameKeyCode(key))
                return "DFU shortcut " + button;
        return null;
    }

    private static KeyCode ReadKey(ModSettings source, string name, KeyCode fallback)
    {
        string text = source.GetString("Controls", name);
        KeyCode key;
        if (!string.IsNullOrEmpty(text) && Enum.TryParse<KeyCode>(text.Trim(), true, out key) && Enum.IsDefined(typeof(KeyCode), key))
        {
            string conflict = ShortcutConflict(key);
            if (conflict == null) return key;
            Debug.LogWarning("[CinematicCamera] " + name + " " + key + " conflicts with " + conflict + ". Replacing it.");
        }
        else Debug.LogWarning("[CinematicCamera] Invalid " + name + " '" + text + "'. Replacing it.");
        // Never replace a conflict with another occupied key.
        return ShortcutConflict(fallback) == null ? fallback : KeyCode.None;
    }

    private void LoadSettings(ModSettings source, ModSettingsChange change)
    {
        settings = CinematicCameraSettings.Read(source);
        toggleKey = ReadKey(source, "ToggleKey", KeyCode.Keypad1);
        nextShotKey = ReadKey(source, "NextShotKey", KeyCode.Keypad2);
        if (nextShotKey != KeyCode.None && nextShotKey == toggleKey)
            nextShotKey = toggleKey != KeyCode.Keypad2 && ShortcutConflict(KeyCode.Keypad2) == null ? KeyCode.Keypad2 : KeyCode.None;
        // Repair old defaults in DFU's saved settings too, so the menu shows the
        // keys actually in use. Keep the user's framing and transition values.
        if (source.GetString("Controls", "ToggleKey") != toggleKey.ToString() ||
            source.GetString("Controls", "NextShotKey") != nextShotKey.ToString())
        {
            var saved = ModSettingsData.Make(mod);
            saved.LoadLocalValues();
            saved.Sections["Controls"].Keys["ToggleKey"].TextValue = toggleKey.ToString();
            saved.Sections["Controls"].Keys["NextShotKey"].TextValue = nextShotKey.ToString();
            saved.Save();
        }
        director.Reset();
        ready = false;
        Debug.Log("[CinematicCamera] Settings loaded. Toggle: " + toggleKey + "; next: " + nextShotKey + ".");
    }

    private void OpenSettings()
    {
        if (mod == null || !mod.HasSettings) return;
        Restore();
        ready = false;
        // liveChange=true invokes LoadSettingsCallback when Save is clicked.
        var ui = DaggerfallUI.UIManager;
        ui.PushWindow(new ModSettingsWindow(ui, mod, true));
    }

    private void OnEnable()
    {
        Camera.onPreCull += BeforeCamera;
        Camera.onPostRender += AfterCamera;
    }

    private void SetEnabled(bool value)
    {
        Restore();
        requested = value;
        ready = false;
        director.Reset();
        status = value ? "Waiting for outdoor, on-foot gameplay" : "Off";
        Debug.Log("[CinematicCamera] " + status);
        DaggerfallUI.AddHUDText(value ? "Cinematic camera on" : "Cinematic camera off");
        PublishControlStatus(true);
    }

    private void ReceiveMessage(string message, object data, DFModMessageCallback callback)
    {
        switch (message.ToLowerInvariant())
        {
            case "on": SetEnabled(true); break;
            case "off": SetEnabled(false); break;
            case "toggle": SetEnabled(!requested); break;
            case "next": director.Next(); break;
            case "settings": OpenSettings(); break;
        }
        if (callback != null) callback("status", status);
    }

    private void Update()
    {
        // Fallback if a render was interrupted or its camera was disabled.
        if (overlaidCamera != null && overlayFrame < Time.frameCount) Restore();
        // Explicit bot requests work in menus as well, without synthetic keys.
        PollControlBridge();
        var game = GameManager.Instance;
        // Do not act on keys typed into DFU's menus or the settings text fields.
        if (game == null || !game.IsPlayingGame() || !game.IsPlayerOnHUD) return;
        if (HotkeySequence.GetKeyboardKeyModifiers() != HotkeySequence.KeyModifiers.None) return;
        if (ShortcutPressed(toggleKey)) SetEnabled(!requested);
        else if (ShortcutPressed(nextShotKey)) director.Next();
    }

    private static bool ShortcutPressed(KeyCode key)
    {
        if (key == KeyCode.None || !Input.GetKeyDown(key)) return false;
        string conflict = ShortcutConflict(key);
        if (conflict == null) return true;
        Debug.LogWarning("[CinematicCamera] Ignoring " + key + ": now used by " + conflict + ". Choose another key in mod settings.");
        return false;
    }

    private void LateUpdate()
    {
        ready = false;
        if (!requested) return;
        var game = GameManager.Instance;
        if (game == null || !game.IsPlayingGame() || !game.IsPlayerOnHUD ||
            game.PlayerMotor == null || game.TransportManager == null || !game.TransportManager.IsOnFoot ||
            game.PlayerEnterExit == null || game.IsPlayerInside || game.PlayerEntity == null || game.PlayerEntity.CurrentHealth <= 0)
        {
            director.Reset();
            status = "Suspended (menu, indoors, mounted, or loading)";
            return;
        }
        Camera camera = game.MainCamera;
        if (camera == null || !camera.isActiveAndEnabled) return;
        float dt = Time.deltaTime;
        // Skip stalls; retain the shot rather than integrating a large camera jump.
        if (dt <= 0 || dt > 0.25f) return;
        if (mainCamera != camera) { director.Reset(); mainCamera = camera; }
        CharacterController controller = game.PlayerController;
        if (controller == null) return;
        Vector3 feet = controller.transform.TransformPoint(controller.center) - Vector3.up * (controller.height * 0.5f);
        director.Update(dt, feet, game.PlayerMotor.transform.forward, settings);
        Vector3 desired = director.Position;
        float lift = GroundLift(desired);
        terrainLift = director.Cut ? lift : Math.Max(lift, terrainLift * (float)Math.Exp(-2 * dt));
        position = desired + Vector3.up * terrainLift;
        rotation = Quaternion.LookRotation(director.Target - position, Vector3.up);
        ready = true;
        status = director.CurrentShot.ToString();
    }

    private float GroundLift(Vector3 desired)
    {
        // Match NMW's terrain-only clearance. Props and trees must not continually
        // collapse distant shots into close-ups. No allocating queries per frame.
        int count = Physics.RaycastNonAlloc(desired + Vector3.up * 256, Vector3.down,
            hits, 256.35f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
        float lift = 0;
        for (int i = 0; i < count; i++)
            if (hits[i].collider is TerrainCollider)
                lift = Math.Max(lift, hits[i].point.y + 0.35f - desired.y);
        return lift;
    }

    private void BeforeCamera(Camera camera)
    {
        if (!ready || !requested || mainCamera == null ||
            camera.cameraType != CameraType.Game || overlaidCamera != null) return;
        // DFU's sky pass renders before MainCamera and reads MainCamera's angles.
        // Give each game render pass the same view, including that sky pass.
        Transform transform = mainCamera.transform;
        originalParent = transform.parent;
        originalLocalPosition = transform.localPosition;
        originalLocalRotation = transform.localRotation;
        overlaidCamera = mainCamera;
        renderPassCamera = camera;
        overlayFrame = Time.frameCount;
        writtenPosition = position;
        writtenRotation = rotation;
        transform.SetPositionAndRotation(position, rotation);
        if (camera == mainCamera)
            eyeBillboard.Apply(position, transform.forward, GameManager.Instance.PlayerMotor.transform.forward);
    }

    private void AfterCamera(Camera camera)
    {
        if (camera == renderPassCamera) Restore();
    }

    private void Restore()
    {
        eyeBillboard.Restore();
        if (overlaidCamera != null)
        {
            Transform transform = overlaidCamera.transform;
            // Do not overwrite a different camera system's subsequent changes.
            if (transform.parent == originalParent && (transform.position - writtenPosition).sqrMagnitude < 0.000001f &&
                Quaternion.Angle(transform.rotation, writtenRotation) < 0.01f)
            {
                transform.localPosition = originalLocalPosition;
                transform.localRotation = originalLocalRotation;
            }
        }
        overlaidCamera = null;
        renderPassCamera = null;
    }

    private void OnDisable()
    {
        Restore();
        ready = false;
        PublishControlStatus(false);
        Camera.onPreCull -= BeforeCamera;
        Camera.onPostRender -= AfterCamera;
    }

    private void OnApplicationQuit() { PublishControlStatus(false); }

    private void OnDestroy()
    {
        Restore();
        if (mod != null)
        {
            mod.MessageReceiver = null;
            mod.LoadSettingsCallback = null;
        }
    }
}
