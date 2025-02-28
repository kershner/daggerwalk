using UnityEngine;
using DaggerfallWorkshop;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;
using DaggerfallWorkshop.Game.Serialization;

public class FasterNights : MonoBehaviour
{
    private bool isInitialized = false;
    private bool saveLoaded = false;
    public static Mod mod;
    
    // Day/Night Timescale settings
    private const float DAY_TIMESCALE = 12f;    // Default timescale during day
    private const float NIGHT_TIMESCALE = 120f;  // Faster timescale during night  - 6 minutes
    private const int NIGHT_HOUR = 18;          // 6pm in 24-hour format
    private const int DAY_HOUR = 6;             // 6am in 24-hour format
    
    // Debug settings
    private const bool VERBOSE_LOGGING = true;  // Set to true for detailed logs
    
    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        Debug.Log("[FasterNights] Init() was called! Registering mod...");
        mod = initParams.Mod;
        mod.IsReady = true;
        
        var go = new GameObject(mod.Title);
        go.AddComponent<FasterNights>();
        
        Debug.Log("[FasterNights] GameObject created and component attached.");
    }

    void Awake()
    {
        Debug.Log("[FasterNights] Awake() called.");
        
        // Log mod configuration
        Debug.Log($"[FasterNights] Configuration: DAY_TIMESCALE={DAY_TIMESCALE}, NIGHT_TIMESCALE={NIGHT_TIMESCALE}");
        Debug.Log($"[FasterNights] Configuration: DAY_HOUR={DAY_HOUR}, NIGHT_HOUR={NIGHT_HOUR}");
        Debug.Log($"[FasterNights] Verbose logging is {(VERBOSE_LOGGING ? "enabled" : "disabled")}");
        
        Debug.Log("[FasterNights] Subscribing to StreamingWorld.OnInitWorld event");
        StreamingWorld.OnInitWorld += InitializeTimeScale;
        
        Debug.Log("[FasterNights] Subscribing to SaveLoadManager.OnLoad event");
        SaveLoadManager.OnLoad += SaveLoaded;
        
        Debug.Log("[FasterNights] Awake() completed");
    }

    void SaveLoaded(SaveData_v1 saveData)
    {
        saveLoaded = true;
        Debug.Log("[FasterNights] Save loaded event fired, enabling time scaling.");
        
        // Log player info from save
        if (GameManager.Instance != null && GameManager.Instance.PlayerEntity != null)
        {
            Debug.Log($"[FasterNights] Player name: {GameManager.Instance.PlayerEntity.Name}");
            Debug.Log($"[FasterNights] Player level: {GameManager.Instance.PlayerEntity.Level}");
        }
        
        // Get current time info
        if (DaggerfallUnity.Instance != null && DaggerfallUnity.Instance.WorldTime != null)
        {
            var now = DaggerfallUnity.Instance.WorldTime.Now;
            Debug.Log($"[FasterNights] Game time at load: {now.Hour}:{now.Minute:D2} on {now.DayName}, {now.DayOfMonth} {now.MonthName}, 3E {now.Year}");
            Debug.Log($"[FasterNights] Current timescale: {DaggerfallUnity.Instance.WorldTime.TimeScale}");
        }
        else
        {
            Debug.LogWarning("[FasterNights] Unable to get time information - WorldTime may be null");
        }
        
        // Subscribe to time events
        Debug.Log("[FasterNights] Subscribing to WorldTime.OnNewHour event");
        DaggerfallWorkshop.WorldTime.OnNewHour += CheckTimeOfDay;
        
        // Set initial timescale based on current time of day
        Debug.Log("[FasterNights] Setting initial timescale");
        SetInitialTimescale();
        
        Debug.Log("[FasterNights] Save loaded handling completed");
    }

    void InitializeTimeScale()
    {
        Debug.Log("[FasterNights] InitializeTimeScale() called.");
        
        if (isInitialized)
        {
            Debug.LogWarning("[FasterNights] Already initialized. Skipping.");
            return;
        }

        if (GameManager.Instance == null)
        {
            Debug.LogError("[FasterNights] GameManager is null! Cannot initialize.");
            return;
        }

        isInitialized = true;
        Debug.Log("[FasterNights] Initialization complete. Waiting for save load...");

        if (saveLoaded)
        {
            // Subscribe to time events
            Debug.Log("[FasterNights] saveLoaded is true, subscribing to WorldTime.OnNewHour event");
            DaggerfallWorkshop.WorldTime.OnNewHour += CheckTimeOfDay;
            
            // Set initial timescale based on current time of day
            Debug.Log("[FasterNights] Setting initial timescale after initialization");
            SetInitialTimescale();
        }
        else
        {
            Debug.Log("[FasterNights] saveLoaded is false, will wait for save to load");
        }
    }

    void OnDestroy()
    {
        Debug.Log("[FasterNights] OnDestroy() called. Unsubscribing events.");
        
        if (isInitialized)
        {
            Debug.Log("[FasterNights] Unsubscribing from StreamingWorld.OnInitWorld");
            StreamingWorld.OnInitWorld -= InitializeTimeScale;
            
            Debug.Log("[FasterNights] Unsubscribing from SaveLoadManager.OnLoad");
            SaveLoadManager.OnLoad -= SaveLoaded;
            
            Debug.Log("[FasterNights] Unsubscribing from WorldTime.OnNewHour");
            DaggerfallWorkshop.WorldTime.OnNewHour -= CheckTimeOfDay;
        }
        else
        {
            Debug.Log("[FasterNights] Mod was not fully initialized, no event cleanup needed");
        }
        
        Debug.Log("[FasterNights] OnDestroy completed");
    }

    private void SetInitialTimescale()
    {
        if (DaggerfallUnity.Instance == null || DaggerfallUnity.Instance.WorldTime == null)
        {
            Debug.LogError("[FasterNights] DaggerfallUnity or WorldTime is null. Cannot set initial timescale!");
            return;
        }
        
        // Get current hour
        int currentHour = DaggerfallUnity.Instance.WorldTime.Now.Hour;
        Debug.Log($"[FasterNights] Setting initial timescale - current hour is {currentHour}");
        
        // Check if it's day or night and set appropriate timescale
        if (currentHour >= NIGHT_HOUR || currentHour < DAY_HOUR) 
        {
            // It's night time
            Debug.Log($"[FasterNights] Initial time is night ({currentHour}:00), setting night timescale");
            SetNightTimeScale();
        }
        else 
        {
            // It's day time
            Debug.Log($"[FasterNights] Initial time is day ({currentHour}:00), setting day timescale");
            SetDayTimeScale();
        }
    }

    private void CheckTimeOfDay()
    {
        if (!isInitialized || !saveLoaded)
        {
            if (VERBOSE_LOGGING)
            {
                Debug.Log($"[FasterNights] CheckTimeOfDay called, but mod not ready yet. initialized={isInitialized}, saveLoaded={saveLoaded}");
            }
            return;
        }
            
        if (DaggerfallUnity.Instance == null || DaggerfallUnity.Instance.WorldTime == null)
        {
            Debug.LogError("[FasterNights] DaggerfallUnity or WorldTime is null in CheckTimeOfDay!");
            return;
        }
        
        // Get current hour
        int currentHour = DaggerfallUnity.Instance.WorldTime.Now.Hour;
        
        if (VERBOSE_LOGGING)
        {
            Debug.Log($"[FasterNights] CheckTimeOfDay - Hour changed to {currentHour}:00");
            Debug.Log($"[FasterNights] Current timescale is {DaggerfallUnity.Instance.WorldTime.TimeScale}");
        }
        
        // Check if we just transitioned to night (6pm)
        if (currentHour == NIGHT_HOUR)
        {
            Debug.Log($"[FasterNights] Time is now {NIGHT_HOUR}:00 (6pm) - Transitioning to night timescale");
            SetNightTimeScale();
        }
        // Check if we just transitioned to day (6am)
        else if (currentHour == DAY_HOUR)
        {
            Debug.Log($"[FasterNights] Time is now {DAY_HOUR}:00 (6am) - Transitioning to day timescale");
            SetDayTimeScale();
        }
        else if (VERBOSE_LOGGING)
        {
            Debug.Log($"[FasterNights] Hour is {currentHour}, no timescale change needed");
        }
    }
    
    private void SetDayTimeScale()
    {
        if (DaggerfallUnity.Instance == null || DaggerfallUnity.Instance.WorldTime == null)
        {
            Debug.LogError("[FasterNights] DaggerfallUnity or WorldTime is null in SetDayTimeScale!");
            return;
        }
        
        float currentScale = DaggerfallUnity.Instance.WorldTime.TimeScale;
        Debug.Log($"[FasterNights] Setting day timescale - current={currentScale}, target={DAY_TIMESCALE}");
        
        if (currentScale != DAY_TIMESCALE)
        {
            DaggerfallUnity.Instance.WorldTime.TimeScale = DAY_TIMESCALE;
            Debug.Log($"[FasterNights] Day timescale set to {DAY_TIMESCALE}");
            // Verify the change was applied
            Debug.Log($"[FasterNights] Verified new timescale: {DaggerfallUnity.Instance.WorldTime.TimeScale}");
        }
        else
        {
            Debug.Log($"[FasterNights] Day timescale already set to {DAY_TIMESCALE}, no change needed");
        }
    }
    
    private void SetNightTimeScale()
    {
        if (DaggerfallUnity.Instance == null || DaggerfallUnity.Instance.WorldTime == null)
        {
            Debug.LogError("[FasterNights] DaggerfallUnity or WorldTime is null in SetNightTimeScale!");
            return;
        }
        
        float currentScale = DaggerfallUnity.Instance.WorldTime.TimeScale;
        Debug.Log($"[FasterNights] Setting night timescale - current={currentScale}, target={NIGHT_TIMESCALE}");
        
        if (currentScale != NIGHT_TIMESCALE)
        {
            DaggerfallUnity.Instance.WorldTime.TimeScale = NIGHT_TIMESCALE;
            Debug.Log($"[FasterNights] Night timescale set to {NIGHT_TIMESCALE}");
            // Verify the change was applied
            Debug.Log($"[FasterNights] Verified new timescale: {DaggerfallUnity.Instance.WorldTime.TimeScale}");
        }
        else
        {
            Debug.Log($"[FasterNights] Night timescale already set to {NIGHT_TIMESCALE}, no change needed");
        }
    }
    
    void Update()
    {
        // Only log occasionally if verbose logging is enabled
        if (VERBOSE_LOGGING && Time.frameCount % 1000 == 0 && isInitialized && saveLoaded)
        {
            if (DaggerfallUnity.Instance != null && DaggerfallUnity.Instance.WorldTime != null)
            {
                var now = DaggerfallUnity.Instance.WorldTime.Now;
                Debug.Log($"[FasterNights] Current time: {now.Hour}:{now.Minute:D2}, Timescale: {DaggerfallUnity.Instance.WorldTime.TimeScale}");
            }
        }
    }
}