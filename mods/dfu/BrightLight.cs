using System;
using System.Globalization;
using UnityEngine;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;
using Wenzil.Console;
using Wenzil.Console.Commands;

// Player-mounted, highly configurable light for Daggerfall Unity.
// Press semicolon to toggle it. Use "brightlight help" in the DFU console
// to tune it live; settings are persisted with Unity PlayerPrefs.
[DisallowMultipleComponent]
public class BrightLight : MonoBehaviour
{
    public static Mod mod;
    private static BrightLight instance;

    // Defaults used on first launch and by "brightlight reset".
    private const KeyCode DefaultToggleKey = KeyCode.Semicolon;
    private const bool DefaultEnabled = false;
    private const float DefaultIntensity = 8f;
    private const float DefaultRange = 100f;
    private const float DefaultBounce = 1f;
    private const float DefaultRed = 1f;
    private const float DefaultGreen = 0.96f;
    private const float DefaultBlue = 0.84f;
    private const float DefaultOffsetX = 0f;
    private const float DefaultOffsetY = 0.15f;
    private const float DefaultOffsetZ = 0.35f;
    private const float DefaultFlickerAmount = 0f;
    private const float DefaultFlickerSpeed = 8f;
    private const float DefaultSpotAngle = 80f;
    private const float DefaultShadowStrength = 0.8f;
    private const float DefaultShadowBias = 0.05f;
    private const float DefaultShadowNormalBias = 0.4f;
    private const float DefaultShadowNearPlane = 0.2f;

    private const string PrefPrefix = "Daggerwalk.BrightLight.";

    private GameObject lightObject;
    private Light playerLight;
    private Transform attachedCamera;
    private KeyCode toggleKey = DefaultToggleKey;
    private bool lightEnabled = DefaultEnabled;
    private float baseIntensity = DefaultIntensity;
    private float lightRange = DefaultRange;
    private float bounceIntensity = DefaultBounce;
    private Color lightColor = new Color(DefaultRed, DefaultGreen, DefaultBlue, 1f);
    private Vector3 localOffset = new Vector3(DefaultOffsetX, DefaultOffsetY, DefaultOffsetZ);
    private float flickerAmount = DefaultFlickerAmount;
    private float flickerSpeed = DefaultFlickerSpeed;
    private LightType lightType = LightType.Point;
    private float spotAngle = DefaultSpotAngle;
    private LightShadows shadowType = LightShadows.None;
    private float shadowStrength = DefaultShadowStrength;
    private float shadowBias = DefaultShadowBias;
    private float shadowNormalBias = DefaultShadowNormalBias;
    private float shadowNearPlane = DefaultShadowNearPlane;
    private bool useColorTemperature = false;
    private float colorTemperature = 5500f;
    private int cullingMask = -1;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;

        GameObject oldObject = GameObject.Find(mod.Title);
        if (oldObject != null)
            UnityEngine.Object.Destroy(oldObject);

        GameObject go = new GameObject(mod.Title);
        UnityEngine.Object.DontDestroyOnLoad(go);
        go.AddComponent<BrightLight>();
        mod.IsReady = true;
    }

    private void Awake()
    {
        instance = this;
        LoadSettings();
        RegisterConsoleCommand();
        EnsureLight();
        ApplySettings();
        Debug.Log("[BrightLight] Ready. Press ; to toggle or enter 'brightlight help'.");
    }

    private void OnDestroy()
    {
        if (instance == this)
            instance = null;
        if (lightObject != null)
            Destroy(lightObject);
    }

    private void Update()
    {
        if (Input.GetKeyDown(toggleKey))
            SetEnabled(!lightEnabled);

        EnsureLight();

        if (playerLight != null && lightEnabled && flickerAmount > 0f)
        {
            float noise = Mathf.PerlinNoise(Time.unscaledTime * flickerSpeed, 0.173f);
            float multiplier = Mathf.Lerp(1f - flickerAmount, 1f + flickerAmount, noise);
            playerLight.intensity = baseIntensity * multiplier;
        }
    }

    private static void RegisterConsoleCommand()
    {
        ConsoleCommandsDatabase.RegisterCommand(
            "brightlight",
            "Controls the configurable player-mounted light.",
            "brightlight help",
            ExecuteConsoleCommand);
    }

    private void EnsureLight()
    {
        Camera camera = Camera.main;
        if (camera == null)
            return;

        if (lightObject == null)
        {
            lightObject = new GameObject("Daggerwalk Bright Light");
            playerLight = lightObject.AddComponent<Light>();
            ApplySettings();
        }

        if (attachedCamera != camera.transform)
        {
            attachedCamera = camera.transform;
            lightObject.transform.SetParent(attachedCamera, false);
            lightObject.transform.localPosition = localOffset;
            lightObject.transform.localRotation = Quaternion.identity;
        }
    }

    private void ApplySettings()
    {
        if (playerLight == null)
            return;

        playerLight.enabled = lightEnabled;
        playerLight.type = lightType;
        playerLight.intensity = baseIntensity;
        playerLight.range = lightRange;
        playerLight.bounceIntensity = bounceIntensity;
        playerLight.color = lightColor;
        playerLight.spotAngle = spotAngle;
        playerLight.shadows = shadowType;
        playerLight.shadowStrength = shadowStrength;
        playerLight.shadowBias = shadowBias;
        playerLight.shadowNormalBias = shadowNormalBias;
        playerLight.shadowNearPlane = shadowNearPlane;
        playerLight.renderMode = LightRenderMode.ForcePixel;
        playerLight.cullingMask = cullingMask;
        playerLight.useColorTemperature = useColorTemperature;
        if (useColorTemperature)
            playerLight.colorTemperature = colorTemperature;

        if (lightObject != null)
            lightObject.transform.localPosition = localOffset;
    }

    private void SetEnabled(bool value)
    {
        lightEnabled = value;
        if (playerLight != null)
        {
            playerLight.enabled = value;
            playerLight.intensity = baseIntensity;
        }
        SaveSettings();
        Debug.Log("[BrightLight] " + (value ? "ON" : "OFF"));
    }

    private static string ExecuteConsoleCommand(string[] args)
    {
        if (instance == null)
            return "BrightLight is not initialized yet.";

        if (args == null || args.Length == 0)
            return instance.Status();

        string command = args[0].ToLowerInvariant();
        try
        {
            if (command == "help")
                return HelpText();
            if (command == "status")
                return instance.Status();
            if (command == "on" || command == "off" || command == "toggle")
            {
                instance.SetEnabled(command == "toggle" ? !instance.lightEnabled : command == "on");
                return instance.Status();
            }
            if (command == "reset")
            {
                instance.ResetSettings();
                return "BrightLight reset. " + instance.Status();
            }
            if (command == "preset")
                return instance.SetPreset(args);
            if (command == "intensity")
                instance.baseIntensity = ParseFloat(args, 1, 0f, 100f, "intensity");
            else if (command == "range")
                instance.lightRange = ParseFloat(args, 1, 0.1f, 500f, "range");
            else if (command == "bounce")
                instance.bounceIntensity = ParseFloat(args, 1, 0f, 8f, "bounce");
            else if (command == "color")
                instance.lightColor = ParseColor(args);
            else if (command == "temperature")
                instance.SetTemperature(args);
            else if (command == "type")
                instance.SetType(args);
            else if (command == "spotangle")
                instance.spotAngle = ParseFloat(args, 1, 1f, 179f, "spot angle");
            else if (command == "offset")
                instance.localOffset = new Vector3(
                    ParseFloat(args, 1, -10f, 10f, "offset x"),
                    ParseFloat(args, 2, -10f, 10f, "offset y"),
                    ParseFloat(args, 3, -10f, 10f, "offset z"));
            else if (command == "flicker")
            {
                instance.flickerAmount = ParseFloat(args, 1, 0f, 1f, "flicker amount");
                instance.flickerSpeed = ParseFloat(args, 2, 0.01f, 100f, "flicker speed");
            }
            else if (command == "shadows")
                instance.SetShadows(args);
            else if (command == "shadowstrength")
                instance.shadowStrength = ParseFloat(args, 1, 0f, 1f, "shadow strength");
            else if (command == "shadowbias")
                instance.shadowBias = ParseFloat(args, 1, 0f, 2f, "shadow bias");
            else if (command == "normalbias")
                instance.shadowNormalBias = ParseFloat(args, 1, 0f, 3f, "shadow normal bias");
            else if (command == "nearplane")
                instance.shadowNearPlane = ParseFloat(args, 1, 0.01f, 10f, "shadow near plane");
            else if (command == "key")
                instance.SetKey(args);
            else
                return "Unknown option '" + args[0] + "'. Enter: brightlight help";

            instance.ApplySettings();
            instance.SaveSettings();
            return instance.Status();
        }
        catch (ArgumentException exception)
        {
            return exception.Message;
        }
    }

    private static string HelpText()
    {
        return
            "BrightLight commands:\n" +
            " brightlight on|off|toggle|status|reset\n" +
            " brightlight preset torch|torch2|torch3\n" +
            " brightlight intensity <0-100>\n" +
            " brightlight range <0.1-500>\n" +
            " brightlight color <red> <green> <blue>  (0-255)\n" +
            " brightlight temperature <1000-20000>|off\n" +
            " brightlight type point|spot\n" +
            " brightlight spotangle <1-179>\n" +
            " brightlight offset <x> <y> <z>\n" +
            " brightlight flicker <amount 0-1> <speed>\n" +
            " brightlight bounce <0-8>\n" +
            " brightlight shadows off|hard|soft\n" +
            " brightlight shadowstrength|shadowbias|normalbias|nearplane <value>\n" +
            " brightlight key <Unity KeyCode name>  (default: Semicolon)";
    }

    private string Status()
    {
        return string.Format(CultureInfo.InvariantCulture,
            "BrightLight {0} | key={1} type={2} intensity={3:0.##} range={4:0.##} " +
            "color={5:0},{6:0},{7:0} temp={8} shadows={9} flicker={10:0.##}@{11:0.##}",
            lightEnabled ? "ON" : "OFF", toggleKey, lightType, baseIntensity, lightRange,
            lightColor.r * 255f, lightColor.g * 255f, lightColor.b * 255f,
            useColorTemperature ? colorTemperature.ToString("0", CultureInfo.InvariantCulture) + "K" : "off",
            shadowType, flickerAmount, flickerSpeed);
    }

    private string SetPreset(string[] args)
    {
        RequireArgs(args, 2, "Usage: brightlight preset torch|torch2|torch3");
        string preset = args[1].ToLowerInvariant();
        float intensityMultiplier;
        if (preset == "torch")
            intensityMultiplier = 1f;
        else if (preset == "torch2")
            intensityMultiplier = 2f;
        else if (preset == "torch3")
            intensityMultiplier = 3f;
        else
            throw new ArgumentException("Unknown preset. Use torch, torch2, or torch3.");

        // All three levels retain the original torch character. Only its output
        // intensity changes, so color, reach, and flicker remain consistent.
        {
            baseIntensity = 1.6f * intensityMultiplier; lightRange = 24f;
            lightColor = new Color(1f, 0.72f, 0.42f); flickerAmount = 0.08f; flickerSpeed = 9f;
        }

        lightType = LightType.Point;
        ApplySettings(); SaveSettings();
        return "Preset applied: " + preset + ". " + Status();
    }

    private void SetTemperature(string[] args)
    {
        RequireArgs(args, 2, "Usage: brightlight temperature <1000-20000>|off");
        if (args[1].ToLowerInvariant() == "off")
            useColorTemperature = false;
        else
        {
            colorTemperature = ParseFloat(args, 1, 1000f, 20000f, "color temperature");
            useColorTemperature = true;
        }
    }

    private void SetType(string[] args)
    {
        RequireArgs(args, 2, "Usage: brightlight type point|spot");
        string value = args[1].ToLowerInvariant();
        if (value == "point") lightType = LightType.Point;
        else if (value == "spot") lightType = LightType.Spot;
        else throw new ArgumentException("Light type must be point or spot.");
    }

    private void SetShadows(string[] args)
    {
        RequireArgs(args, 2, "Usage: brightlight shadows off|hard|soft");
        string value = args[1].ToLowerInvariant();
        if (value == "off" || value == "none") shadowType = LightShadows.None;
        else if (value == "hard") shadowType = LightShadows.Hard;
        else if (value == "soft") shadowType = LightShadows.Soft;
        else throw new ArgumentException("Shadows must be off, hard, or soft.");
    }

    private void SetKey(string[] args)
    {
        RequireArgs(args, 2, "Usage: brightlight key <Unity KeyCode name>");
        try { toggleKey = (KeyCode)Enum.Parse(typeof(KeyCode), args[1], true); }
        catch { throw new ArgumentException("Unknown key name: " + args[1]); }
    }

    private static Color ParseColor(string[] args)
    {
        float r = ParseFloat(args, 1, 0f, 255f, "red");
        float g = ParseFloat(args, 2, 0f, 255f, "green");
        float b = ParseFloat(args, 3, 0f, 255f, "blue");
        return new Color(r / 255f, g / 255f, b / 255f, 1f);
    }

    private static float ParseFloat(string[] args, int index, float min, float max, string name)
    {
        RequireArgs(args, index + 1, "Missing " + name + " value.");
        float value;
        if (!float.TryParse(args[index], NumberStyles.Float, CultureInfo.InvariantCulture, out value))
            throw new ArgumentException("Invalid " + name + ": " + args[index]);
        if (value < min || value > max)
            throw new ArgumentException(name + " must be between " + min + " and " + max + ".");
        return value;
    }

    private static void RequireArgs(string[] args, int count, string message)
    {
        if (args == null || args.Length < count)
            throw new ArgumentException(message);
    }

    private void ResetSettings()
    {
        toggleKey = DefaultToggleKey; lightEnabled = DefaultEnabled;
        baseIntensity = DefaultIntensity; lightRange = DefaultRange; bounceIntensity = DefaultBounce;
        lightColor = new Color(DefaultRed, DefaultGreen, DefaultBlue, 1f);
        localOffset = new Vector3(DefaultOffsetX, DefaultOffsetY, DefaultOffsetZ);
        flickerAmount = DefaultFlickerAmount; flickerSpeed = DefaultFlickerSpeed;
        lightType = LightType.Point; spotAngle = DefaultSpotAngle; shadowType = LightShadows.None;
        shadowStrength = DefaultShadowStrength; shadowBias = DefaultShadowBias;
        shadowNormalBias = DefaultShadowNormalBias; shadowNearPlane = DefaultShadowNearPlane;
        useColorTemperature = false; colorTemperature = 5500f; cullingMask = -1;
        ApplySettings(); SaveSettings();
    }

    private void SaveSettings()
    {
        PlayerPrefs.SetInt(PrefPrefix + "Enabled", lightEnabled ? 1 : 0);
        PlayerPrefs.SetInt(PrefPrefix + "Key", (int)toggleKey);
        PlayerPrefs.SetFloat(PrefPrefix + "Intensity", baseIntensity);
        PlayerPrefs.SetFloat(PrefPrefix + "Range", lightRange);
        PlayerPrefs.SetFloat(PrefPrefix + "Bounce", bounceIntensity);
        PlayerPrefs.SetFloat(PrefPrefix + "Red", lightColor.r);
        PlayerPrefs.SetFloat(PrefPrefix + "Green", lightColor.g);
        PlayerPrefs.SetFloat(PrefPrefix + "Blue", lightColor.b);
        PlayerPrefs.SetFloat(PrefPrefix + "OffsetX", localOffset.x);
        PlayerPrefs.SetFloat(PrefPrefix + "OffsetY", localOffset.y);
        PlayerPrefs.SetFloat(PrefPrefix + "OffsetZ", localOffset.z);
        PlayerPrefs.SetFloat(PrefPrefix + "FlickerAmount", flickerAmount);
        PlayerPrefs.SetFloat(PrefPrefix + "FlickerSpeed", flickerSpeed);
        PlayerPrefs.SetInt(PrefPrefix + "Type", (int)lightType);
        PlayerPrefs.SetFloat(PrefPrefix + "SpotAngle", spotAngle);
        PlayerPrefs.SetInt(PrefPrefix + "Shadows", (int)shadowType);
        PlayerPrefs.SetFloat(PrefPrefix + "ShadowStrength", shadowStrength);
        PlayerPrefs.SetFloat(PrefPrefix + "ShadowBias", shadowBias);
        PlayerPrefs.SetFloat(PrefPrefix + "NormalBias", shadowNormalBias);
        PlayerPrefs.SetFloat(PrefPrefix + "NearPlane", shadowNearPlane);
        PlayerPrefs.SetInt(PrefPrefix + "UseTemperature", useColorTemperature ? 1 : 0);
        PlayerPrefs.SetFloat(PrefPrefix + "Temperature", colorTemperature);
        PlayerPrefs.Save();
    }

    private void LoadSettings()
    {
        lightEnabled = PlayerPrefs.GetInt(PrefPrefix + "Enabled", DefaultEnabled ? 1 : 0) != 0;
        toggleKey = (KeyCode)PlayerPrefs.GetInt(PrefPrefix + "Key", (int)DefaultToggleKey);
        baseIntensity = PlayerPrefs.GetFloat(PrefPrefix + "Intensity", DefaultIntensity);
        lightRange = PlayerPrefs.GetFloat(PrefPrefix + "Range", DefaultRange);
        bounceIntensity = PlayerPrefs.GetFloat(PrefPrefix + "Bounce", DefaultBounce);
        lightColor = new Color(
            PlayerPrefs.GetFloat(PrefPrefix + "Red", DefaultRed),
            PlayerPrefs.GetFloat(PrefPrefix + "Green", DefaultGreen),
            PlayerPrefs.GetFloat(PrefPrefix + "Blue", DefaultBlue), 1f);
        localOffset = new Vector3(
            PlayerPrefs.GetFloat(PrefPrefix + "OffsetX", DefaultOffsetX),
            PlayerPrefs.GetFloat(PrefPrefix + "OffsetY", DefaultOffsetY),
            PlayerPrefs.GetFloat(PrefPrefix + "OffsetZ", DefaultOffsetZ));
        flickerAmount = PlayerPrefs.GetFloat(PrefPrefix + "FlickerAmount", DefaultFlickerAmount);
        flickerSpeed = PlayerPrefs.GetFloat(PrefPrefix + "FlickerSpeed", DefaultFlickerSpeed);
        lightType = (LightType)PlayerPrefs.GetInt(PrefPrefix + "Type", (int)LightType.Point);
        spotAngle = PlayerPrefs.GetFloat(PrefPrefix + "SpotAngle", DefaultSpotAngle);
        shadowType = (LightShadows)PlayerPrefs.GetInt(PrefPrefix + "Shadows", (int)LightShadows.None);
        shadowStrength = PlayerPrefs.GetFloat(PrefPrefix + "ShadowStrength", DefaultShadowStrength);
        shadowBias = PlayerPrefs.GetFloat(PrefPrefix + "ShadowBias", DefaultShadowBias);
        shadowNormalBias = PlayerPrefs.GetFloat(PrefPrefix + "NormalBias", DefaultShadowNormalBias);
        shadowNearPlane = PlayerPrefs.GetFloat(PrefPrefix + "NearPlane", DefaultShadowNearPlane);
        useColorTemperature = PlayerPrefs.GetInt(PrefPrefix + "UseTemperature", 0) != 0;
        colorTemperature = PlayerPrefs.GetFloat(PrefPrefix + "Temperature", 5500f);
    }
}
