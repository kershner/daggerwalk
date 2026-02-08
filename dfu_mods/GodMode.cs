using System;
using UnityEngine;
using DaggerfallWorkshop;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;

public class GodMode : MonoBehaviour
{
    public static Mod mod;
    const bool LOG_STATUS = false; // set true while testing
    float nextLogTime = 0f;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;
        mod.IsReady = true;

        var go = new GameObject(mod.Title);
        DontDestroyOnLoad(go);               // persist across loads
        go.AddComponent<GodMode>();
    }

    void Update()
    {
        var gm = GameManager.Instance;
        var player = gm?.PlayerEntity;
        if (player == null) return;

        if (!player.GodMode) player.GodMode = true;
        if (player.CurrentHealth < player.MaxHealth) player.CurrentHealth = player.MaxHealth;
        if (player.CurrentFatigue < player.MaxFatigue) player.CurrentFatigue = player.MaxFatigue;

        // Optional: prevent drowning blackout
        // if (gm.PlayerEnterExit) gm.PlayerEnterExit.BreathMeter = gm.PlayerEnterExit.BreathMeterMax;

        if (LOG_STATUS && Time.time >= nextLogTime)
        {
            Debug.Log($"[GodMode] enforced | God:{player.GodMode} HP:{player.CurrentHealth}/{player.MaxHealth}");
            nextLogTime = Time.time + 2f;
        }
    }
}
