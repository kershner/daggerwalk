using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using DaggerfallWorkshop;                          // DaggerfallUnity
using DaggerfallWorkshop.Game;                     // AmbientEffectsPlayer, StateManager
using DaggerfallWorkshop.Game.Utility.ModSupport;  // Mod, [Invoke], InitParams
using DaggerfallConnect.Arena2;                    // SoundClips

[DisallowMultipleComponent]
public class MuteClassicSfx : MonoBehaviour
{
    public static Mod mod;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;
        mod.IsReady = true;

        var existing = GameObject.Find(mod.Title);
        if (existing != null)
            UnityEngine.Object.Destroy(existing);

        var go = new GameObject(mod.Title);
        go.AddComponent<MuteClassicSfx>();
        UnityEngine.Object.DontDestroyOnLoad(go);

        Debug.Log("[MuteClassicSfx] Init() → component attached via dfmod.");
    }
    // -------------------------------------------------------------

    [Header("Mute Lists (edit in Inspector)")]
    [Tooltip("SoundClips enum names to mute (e.g., BirdCall1, BirdCall2). If BOTH lists are empty, defaults will be applied.")]
    public string[] NamesToMute = new string[0];

    [Tooltip("Classic sound indices to mute (0..458).")]
    public int[] IndicesToMute = new int[0];

    [Header("Behavior")]
    [Tooltip("Immediately stop the current ambient one-shot when blocking (prevents the first chirp).")]
    public bool StopCurrentAmbientOnBlock = true;

    [Header("Logging")]
    [Tooltip("Log every ambient play and whether it was blocked.")]
    public bool VerboseLogging = true;

    [Tooltip("Log when a clip's samples are zeroed (first time only).")]
    public bool LogSilenceWrites = true;

    // runtime sets
    private readonly HashSet<int> muteSet = new HashSet<int>();
    private readonly HashSet<int> alreadySilenced = new HashSet<int>();

    // reflection cache: private property "Clip" on AmbientEffectsPlayer.AmbientEffectsEventArgs
    private static PropertyInfo clipPropPI;

    // reflection cache: private AudioSource "ambientAudioSource" on AmbientEffectsPlayer (to stop immediately)
    private static FieldInfo ambientSrcFI;

    void OnEnable()
    {
        BuildMuteSet();
        CacheReflection();
        AmbientEffectsPlayer.OnPlayEffect += OnAmbientPlay;
        if (VerboseLogging) Debug.Log("[MuteClassicSfx] Subscribed to AmbientEffectsPlayer.OnPlayEffect");
    }

    void OnDisable()
    {
        AmbientEffectsPlayer.OnPlayEffect -= OnAmbientPlay;
        if (VerboseLogging) Debug.Log("[MuteClassicSfx] Unsubscribed from AmbientEffectsPlayer.OnPlayEffect");
    }

    void OnValidate()
    {
        BuildMuteSet();
    }

    private void BuildMuteSet()
    {
        muteSet.Clear();

        // If user left both arrays empty, seed with defaults (daytime bird calls)
        bool namesEmpty = NamesToMute == null || NamesToMute.Length == 0;
        bool indicesEmpty = IndicesToMute == null || IndicesToMute.Length == 0;
        if (namesEmpty && indicesEmpty)
        {
            NamesToMute = new[] { "BirdCall1", "BirdCall2" };
            if (VerboseLogging) Debug.Log("[MuteClassicSfx] No mute entries set; defaulting to BirdCall1 & BirdCall2.");
        }

        // Indices
        if (IndicesToMute != null)
        {
            foreach (var i in IndicesToMute)
                if (i >= 0 && i <= 458)
                    muteSet.Add(i);
        }

        // Names -> indices
        if (NamesToMute != null)
        {
            foreach (var name in NamesToMute)
            {
                if (string.IsNullOrWhiteSpace(name)) continue;
                SoundClips sc;
                if (Enum.TryParse<SoundClips>(name.Trim(), out sc))
                {
                    int idx = (int)sc;
                    if (idx >= 0 && idx <= 458)
                        muteSet.Add(idx);
                }
            }
        }

        if (VerboseLogging) Debug.Log(string.Format("[MuteClassicSfx] Mute set contains {0} entries.", muteSet.Count));
    }

    private static void CacheReflection()
    {
        if (clipPropPI == null)
        {
            var argsType = typeof(AmbientEffectsPlayer).GetNestedType("AmbientEffectsEventArgs", BindingFlags.Public | BindingFlags.NonPublic);
            if (argsType != null)
                clipPropPI = argsType.GetProperty("Clip", BindingFlags.Instance | BindingFlags.NonPublic);
        }

        if (ambientSrcFI == null)
            ambientSrcFI = typeof(AmbientEffectsPlayer).GetField("ambientAudioSource", BindingFlags.Instance | BindingFlags.NonPublic);
    }

    private void OnAmbientPlay(AmbientEffectsPlayer.AmbientEffectsEventArgs args)
    {
        SoundClips sc = SoundClips.None;

        // Read private property value (the actual clip enum) - C#6 compatible
        if (clipPropPI != null)
        {
            object val = clipPropPI.GetValue(args, null);
            if (val is SoundClips) // classic 'is' check (no pattern matching)
                sc = (SoundClips)val;
        }

        int idx = (int)sc;
        string name = sc.ToString();
        bool inRange = idx >= 0 && idx <= 458;
        bool shouldBlock = inRange && muteSet.Contains(idx);

        if (VerboseLogging)
        {
            if (inRange)
                Debug.Log(string.Format("[MuteClassicSfx] Ambient play: index={0} name={1} → {2}", idx, name, shouldBlock ? "BLOCK" : "allow"));
            else
                Debug.Log(string.Format("[MuteClassicSfx] Ambient play: index(out-of-range) name={0}", name));
        }

        if (shouldBlock)
        {
            // 1) Stop the current ambient source immediately (prevents this instance from sounding)
            if (StopCurrentAmbientOnBlock && ambientSrcFI != null)
            {
                var players = GameObject.FindObjectsOfType<AmbientEffectsPlayer>();
                foreach (var p in players)
                {
                    try
                    {
                        var src = ambientSrcFI.GetValue(p) as AudioSource;
                        if (src != null && src.isPlaying)
                            src.Stop();
                    }
                    catch { }
                }
            }

            // 2) Zero samples globally so subsequent plays of this index are silent
            TrySilenceIndex(idx, name);
        }
    }

    private void TrySilenceIndex(int idx, string nameForLog)
    {
        if (alreadySilenced.Contains(idx)) return;

        var dfu = DaggerfallUnity.Instance;
        if (dfu == null || !dfu.IsReady || dfu.SoundReader == null) return;

        try
        {
            var clip = dfu.SoundReader.GetAudioClip(idx);
            if (!clip) return;

            int total = clip.samples * clip.channels;
            if (total <= 0) return;

            var zeros = new float[total];
            clip.SetData(zeros, 0);

            if (LogSilenceWrites)
                Debug.Log(string.Format("[MuteClassicSfx] Silenced samples for {0} (index {1}) len={2}@{3}", nameForLog, idx, clip.samples, clip.frequency));

            alreadySilenced.Add(idx);
        }
        catch (Exception ex)
        {
            Debug.LogWarning(string.Format("[MuteClassicSfx] Failed to silence index {0}: {1}", idx, ex.Message));
        }
    }
}
