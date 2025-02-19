using System;
using System.IO;
using System.Collections;
using System.Threading.Tasks;
using UnityEngine;
using DaggerfallWorkshop;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;
using DaggerfallWorkshop.Game.Entity;
using DaggerfallWorkshop.Game.Serialization;
using Newtonsoft.Json;
using DaggerfallConnect.Utility;

public class MapDataLogger : MonoBehaviour
{
    private string outputFilePath;
    private bool isInitialized = false;
    private bool saveLoaded = false;
    public static Mod mod;
    
    // Configuration
    private const float UPDATE_INTERVAL_MINUTES = 1f;
    private const int MAX_QUEUE_SIZE = 3;
    
    // Async writing queue management
    private volatile bool isWriting = false;
    private string lastWrittenData = null;
    private string pendingData = null;
    
    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        Debug.Log("MapDataLogger: Init() was called! Registering mod...");
        mod = initParams.Mod;
        mod.IsReady = true;
        
        var go = new GameObject(mod.Title);
        go.AddComponent<MapDataLogger>();
        
        Debug.Log("MapDataLogger: GameObject created and component attached.");
    }

    void Awake()
    {
        outputFilePath = Path.Combine(Application.persistentDataPath, "MapData.json");
        Debug.Log($"MapDataLogger: Awake() called. Output file path set to: {outputFilePath}");

        StreamingWorld.OnInitWorld += InitializeLogger;
        SaveLoadManager.OnLoad += SaveLoaded;
    }

    void SaveLoaded(SaveData_v1 saveData)
    {
        saveLoaded = true;
        Debug.Log("MapDataLogger: Save loaded, enabling logging.");
        LogPlayerPosition(GameManager.Instance.PlayerGPS.CurrentMapPixel); // Immediate first update
        StartCoroutine(PeriodicLogging());
    }

    void InitializeLogger()
    {
        Debug.Log("MapDataLogger: InitializeLogger() called.");
        
        if (isInitialized)
        {
            Debug.LogWarning("MapDataLogger: Already initialized. Skipping.");
            return;
        }

        if (GameManager.Instance == null || GameManager.Instance.PlayerEntity == null || GameManager.Instance.PlayerGPS == null)
        {
            Debug.LogError("MapDataLogger: GameManager or PlayerEntity is null! Cannot initialize.");
            return;
        }

        isInitialized = true;
        Debug.Log("MapDataLogger: Initialization complete. Waiting for save load...");

        if (saveLoaded)
        {
            LogPlayerPosition(GameManager.Instance.PlayerGPS.CurrentMapPixel); // Immediate first update
            StartCoroutine(PeriodicLogging());
        }
    }

    void OnDestroy()
    {
        Debug.Log("MapDataLogger: OnDestroy() called. Unsubscribing events.");
        
        if (isInitialized)
        {
            StreamingWorld.OnInitWorld -= InitializeLogger;
            SaveLoadManager.OnLoad -= SaveLoaded;
            
            // Ensure any pending data is written
            if (pendingData != null)
            {
                WriteDataToDiskAsync(pendingData).ConfigureAwait(false);
            }
        }
    }

    private IEnumerator PeriodicLogging()
    {
        while (isInitialized && saveLoaded)
        {
            yield return new WaitForSeconds(UPDATE_INTERVAL_MINUTES * 60f);
            LogPlayerPosition(GameManager.Instance.PlayerGPS.CurrentMapPixel);
        }
    }

    void LogPlayerPosition(DFPosition mapPixel)
    {
        if (!isInitialized || !saveLoaded)
        {
            Debug.LogWarning("MapDataLogger: Logger not ready. Skipping position log.");
            return;
        }
        
        if (GameManager.Instance == null || GameManager.Instance.PlayerEntity == null || GameManager.Instance.PlayerGPS == null)
        {
            Debug.LogError("MapDataLogger: Critical game components missing! Cannot log data.");
            return;
        }

        var playerGPS = GameManager.Instance.PlayerGPS;
        var weatherManager = GameManager.Instance.WeatherManager;
        var player = GameManager.Instance.PlayerEntity;
        var dfTime = DaggerfallUnity.Instance.WorldTime.Now;

        string dayOfWeek = dfTime.DayName;
        string formattedDate = $"{dayOfWeek}, {dfTime.DayOfMonth} {dfTime.MonthName}, 3E {dfTime.Year}, {dfTime.ShortTimeString()}";
        string realTimeUtc = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss") + " UTC";

        string weather = DetermineWeather(weatherManager);
        string season = GetSeason(dfTime.MonthName);
        string locationName = playerGPS.CurrentLocation.Loaded ? playerGPS.CurrentLocation.Name : "Wilderness";
        string locationType = DetermineLocationType();

        var positionData = new
        {
            playerName = player.Name ?? "Unknown",
            playerRace = player.RaceTemplate?.Name ?? "Unknown Race",
            playerClass = player.Career?.Name ?? "Unknown Class",
            worldX = playerGPS.WorldX,
            worldZ = playerGPS.WorldZ,
            mapPixelX = mapPixel.X,
            mapPixelY = mapPixel.Y,
            region = playerGPS.CurrentRegionName,
            location = locationName,
            locationType = locationType,
            playerX = GameManager.Instance.PlayerObject.transform.position.x,
            playerY = GameManager.Instance.PlayerObject.transform.position.y,
            playerZ = GameManager.Instance.PlayerObject.transform.position.z,
            dayOfWeek = dayOfWeek,
            date = formattedDate,
            realTimeUtc = realTimeUtc,
            season = season,
            weather = weather,
            health = player.CurrentHealth,
            maxHealth = player.MaxHealth,
            fatigue = player.CurrentFatigue,
            magicka = player.CurrentMagicka,
            gold = player.GoldPieces,
            level = player.Level,
            currentSong = GetCurrentSongInfo()
        };

        string jsonData = JsonConvert.SerializeObject(positionData, Formatting.Indented);
        QueueDataWrite(jsonData);
    }

    private void QueueDataWrite(string jsonData)
    {
        // If we're currently writing and already have pending data, skip this update
        if (isWriting && pendingData != null)
        {
            return;
        }

        // If the data is identical to last written data, skip
        if (jsonData == lastWrittenData)
        {
            return;
        }

        // Queue the data
        pendingData = jsonData;

        // If we're not currently writing, start a new write operation
        if (!isWriting)
        {
            _ = WriteDataToDiskAsync(jsonData);
        }
    }

    private async Task WriteDataToDiskAsync(string jsonData)
    {
        if (string.IsNullOrEmpty(jsonData))
            return;

        isWriting = true;

        try
        {
            await Task.Run(() =>
            {
                File.WriteAllText(outputFilePath, jsonData);
            });
            
            lastWrittenData = jsonData;
            
            // Check if more data was queued while we were writing
            if (pendingData != null && pendingData != jsonData)
            {
                string nextData = pendingData;
                pendingData = null;
                _ = WriteDataToDiskAsync(nextData);
            }
            else
            {
                pendingData = null;
                isWriting = false;
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"MapDataLogger: Failed to write file! Exception: {e}");
            isWriting = false;
        }
    }

    private string DetermineWeather(WeatherManager weatherManager)
    {
        if (weatherManager.IsRaining && weatherManager.IsStorming)
            return "Thunderstorm";
        if (weatherManager.IsSnowing && weatherManager.IsStorming)
            return "Blizzard";
        if (weatherManager.IsRaining)
            return "Rainy";
        if (weatherManager.IsSnowing)
            return "Snowy";
        if (weatherManager.IsOvercast)
            return RenderSettings.fogDensity > 0.02f ? "Foggy" : "Cloudy";
        return DaggerfallUnity.Instance.WorldTime.Now.IsDay ? "Sunny" : "Clear";
    }

    private string DetermineLocationType()
    {
        if (GameManager.Instance.PlayerEnterExit.IsPlayerInsideBuilding)
            return "Interior";
        if (GameManager.Instance.IsPlayerInsideDungeon)
            return "Dungeon";
        return GameManager.Instance.PlayerGPS.IsPlayerInTown() ? "Town" : "Wilderness";
    }

    private string GetCurrentSongInfo()
    {
        var songPlayer = FindObjectOfType<DaggerfallSongPlayer>();
        if (songPlayer == null || !songPlayer.IsPlaying)
            return "None";

        // Get current song ID
        return songPlayer.Song.ToString();
    }

    private string GetSeason(string monthName)
    {
        monthName = monthName.Replace("'", "'");

        switch (monthName)
        {
            case "Morning Star":
            case "Sun's Dawn":
            case "First Seed":
                return "Winter";
            case "Rain's Hand":
            case "Second Seed":
            case "Mid Year":
                return "Spring";
            case "Sun's Height":
            case "Last Seed":
            case "Hearthfire":
                return "Summer";
            case "Frostfall":
            case "Sun's Dusk":
            case "Evening Star":
                return "Autumn";
            default:
                Debug.LogError($"MapDataLogger: Unexpected month name: {monthName} - Defaulting to Unknown Season");
                return "Unknown";
        }
    }
}