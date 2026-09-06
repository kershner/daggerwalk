using System;
using System.Collections.Generic;
using UnityEngine;
using DaggerfallWorkshop;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility;
using DaggerfallWorkshop.Game.Utility.ModSupport;
using DaggerfallWorkshop.Game.UserInterfaceWindows;
using Wenzil.Console;
using Wenzil.Console.Commands;

public class MusicChanger : MonoBehaviour
{
    public static Mod mod;
    private static readonly System.Random random = new System.Random();
    private static SongFiles? currentSong = null;
    private static SongManager originalSongManager = null;
    private static bool shuffleMode = false;
    private static int currentSongPlayCount = 0;
    private static int shuffleRepeatsPerSong = 5;
    private static float lastSongStartTime = 0f;
    private static bool isSilenceTrack = false;
    private static float silenceDuration = 90f; // seconds of silence
    private static float silenceTimer = 0f;
    private static int songsSinceLastSilence = 0;
    private static int songsBeforeSilence = 3; // Play silence after every X songs in shuffle mode
    private static string shuffleCategoryFilter = "all"; // Default to all songs
    private static List<string> shuffleCategories = new List<string>() { "all" }; // For multi-category support

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        Debug.Log("MusicChanger: Init() was called! Registering mod...");
        
        mod = initParams.Mod;
        mod.IsReady = true;

        var go = new GameObject(mod.Title);
        go.AddComponent<MusicChanger>();
        
        Debug.Log("MusicChanger: GameObject created and component attached.");
    }

    void Awake()
    {
        Debug.Log("MusicChanger: Awake() called. Registering console commands...");
        ConsoleCommandsDatabase.RegisterCommand("song", "Changes the current music track.", "song <trackNumber/random/shuffle/default/category>\nOr: song shuffle <category1> <category2> ...", ChangeMusic);
        ConsoleCommandsDatabase.RegisterCommand("resume_default", "Resumes default music system.", "resume_default", ResumeDefaultMusic);
    }

    void Update()
    {
        if (currentSong.HasValue)
        {
            var songPlayer = FindObjectOfType<DaggerfallSongPlayer>();
            if (songPlayer != null)
            {
                // Keep SongManager disabled
                if (originalSongManager == null)
                {
                    originalSongManager = FindObjectOfType<SongManager>();
                    if (originalSongManager != null)
                    {
                        originalSongManager.enabled = false;
                        Debug.Log("MusicChanger: Disabled SongManager for custom music playback");
                    }
                }

                // If SongManager got enabled by the game, clear our custom song
                if (originalSongManager != null && originalSongManager.enabled)
                {
                    Debug.Log("MusicChanger: Detected game music change, clearing custom song");
                    currentSong = null;
                    shuffleMode = false;
                    return;
                }

                // Handle silence track (None) differently with a timer
                if (isSilenceTrack)
                {
                    silenceTimer += Time.deltaTime;
                    
                    // When the silence duration is reached, consider it "stopped playing"
                    if (silenceTimer >= silenceDuration)
                    {
                        Debug.Log($"MusicChanger: Silence period completed after {silenceTimer:F2} seconds");
                        silenceTimer = 0f;
                        
                        if (shuffleMode)
                        {
                            HandleSongCompletion(songPlayer);
                        }
                        else
                        {
                            // For non-shuffle mode, restart the silence period
                            lastSongStartTime = Time.time;
                        }
                    }
                }
                // For normal tracks, check if song has stopped
                else if (!songPlayer.IsPlaying)
                {
                    // Log more detailed debug info including the current track and its enum value
                    Debug.Log($"MusicChanger: Song stopped playing. Current song: {currentSong.Value} (ID: {(int)currentSong.Value})");
                    float playDuration = Time.time - lastSongStartTime;
                    Debug.Log($"MusicChanger: Song played for {playDuration:F2} seconds before stopping");
                    
                    if (shuffleMode)
                    {
                        HandleSongCompletion(songPlayer);
                    }
                    else
                    {
                        // For non-shuffle mode, just replay the current song
                        songPlayer.Song = currentSong.Value;
                        songPlayer.Play(currentSong.Value);
                        lastSongStartTime = Time.time;
                    }
                }
            }
        }
    }
    
    private void HandleSongCompletion(DaggerfallSongPlayer songPlayer)
    {
        currentSongPlayCount++;
        
        // Only pick a new song if we've played the current one enough times
        if (currentSongPlayCount >= shuffleRepeatsPerSong)
        {
            // If we're not currently in silence and we've played enough songs
            // since the last silence period, insert a silence period
            if (!isSilenceTrack && shuffleMode && songsSinceLastSilence >= songsBeforeSilence)
            {
                Debug.Log($"MusicChanger: Shuffle mode - Inserting silence period after {songsSinceLastSilence} songs");
                SetupNewSong(SongFiles.song_none);
                songsSinceLastSilence = 0;
                return;
            }
            
            try
            {
                SongFiles newSong;
                
                // Handle multiple category shuffling
                if (shuffleCategories != null && shuffleCategories.Count > 0 && !shuffleCategories.Contains("all"))
                {
                    List<SongFiles> categorySongs = GetSongsInMultipleCategories(shuffleCategories);
                    if (categorySongs != null && categorySongs.Count > 0)
                    {
                        // Pick a random song from the combined categories
                        int index;
                        do {
                            index = random.Next(categorySongs.Count);
                            newSong = categorySongs[index];
                        } while ((int)newSong == (int)currentSong && categorySongs.Count > 1);
                        
                        // Only increment songs since last silence when we're playing a real song (not silence)
                        if ((int)newSong != -1)
                        {
                            songsSinceLastSilence++;
                        }
                        else
                        {
                            // Reset counter if we happen to randomly select silence
                            songsSinceLastSilence = 0;
                        }
                        
                        SetupNewSong(newSong);
                        string categoriesStr = string.Join(", ", shuffleCategories.ToArray());
                        Debug.Log($"MusicChanger: Category shuffle ({categoriesStr}) - Playing new track {currentSong.Value} (ID: {(int)currentSong.Value})");
                        return;
                    }
                }
                // Handle single category shuffle for backward compatibility
                else if (shuffleCategoryFilter != "all")
                {
                    List<SongFiles> categorySongs = GetSongsInCategory(shuffleCategoryFilter);
                    if (categorySongs != null && categorySongs.Count > 0)
                    {
                        // Pick a random song from this category
                        int index;
                        do {
                            index = random.Next(categorySongs.Count);
                            newSong = categorySongs[index];
                        } while ((int)newSong == (int)currentSong && categorySongs.Count > 1);
                        
                        // Only increment songs since last silence when we're playing a real song (not silence)
                        if ((int)newSong != -1)
                        {
                            songsSinceLastSilence++;
                        }
                        else
                        {
                            // Reset counter if we happen to randomly select silence
                            songsSinceLastSilence = 0;
                        }
                        
                        SetupNewSong(newSong);
                        Debug.Log($"MusicChanger: Category shuffle ({shuffleCategoryFilter}) - Playing new track {currentSong.Value} (ID: {(int)currentSong.Value})");
                        return;
                    }
                }
                else // Default shuffle behavior (all categories)
                {
                    // Get all available songs that are explicitly categorized
                    List<SongFiles> allSongs = new List<SongFiles>();
                    foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
                    {
                        // Only include songs that have a recognized category
                        string songCategory = GetSongCategory((int)song);
                        if ((int)song != -1 && songCategory != "Unknown") 
                            allSongs.Add(song);
                    }
                    
                    // Select a random song that's different from the current one if possible
                    do {
                        int index = random.Next(allSongs.Count);
                        newSong = allSongs[index];
                    } while ((int)newSong == (int)currentSong && allSongs.Count > 1);
                    
                    songsSinceLastSilence++;
                    SetupNewSong(newSong);
                    Debug.Log($"MusicChanger: Shuffle mode (all) - Playing new random track {currentSong.Value} (ID: {(int)currentSong.Value})");
                    return;
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"MusicChanger: Error in HandleSongCompletion: {ex.Message}");
                // Fall back to default behavior if an error occurs
            }
            
            // This code should only run if something went wrong with the category logic above
            Debug.LogWarning("MusicChanger: Falling back to default song selection due to an error");
            
            // Get all songs with valid categories
            List<SongFiles> validSongs = new List<SongFiles>();
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                string songCategory = GetSongCategory((int)song);
                if ((int)song != -1 && songCategory != "Unknown")
                    validSongs.Add(song);
            }
            
            // Select a random song from valid songs
            SongFiles newTrack;
            if (validSongs.Count > 0)
            {
                do
                {
                    newTrack = validSongs[random.Next(validSongs.Count)];
                } while ((int)newTrack == (int)currentSong && validSongs.Count > 1); // Avoid same song if possible
            }
            else
            {
                // Fallback to silence if no valid songs found
                newTrack = SongFiles.song_none;
            }
            
            // Only increment songs since last silence when we're playing a real song (not silence)
            if ((int)newTrack != -1)
            {
                songsSinceLastSilence++;
            }
            else
            {
                // Reset counter if we happen to randomly select silence
                songsSinceLastSilence = 0;
            }
            
            // Set up the selected song (handles both normal songs and silence)
            SetupNewSong(newTrack);
            Debug.Log($"MusicChanger: Shuffle mode - Playing new random track {currentSong.Value} (ID: {(int)currentSong.Value})");
        }
        else
        {
            Debug.Log($"MusicChanger: Shuffle mode - Replaying current track {currentSong.Value} (play {currentSongPlayCount + 1} of {shuffleRepeatsPerSong})");
            
            if (isSilenceTrack)
            {
                // Reset silence timer to start a new silence period
                silenceTimer = 0f;
                lastSongStartTime = Time.time;
            }
            else
            {
                // Replay normal song
                songPlayer.Song = currentSong.Value;
                songPlayer.Play(currentSong.Value);
                lastSongStartTime = Time.time;
            }
        }
    }

    // Helper method to get songs in a specific category
    private static List<SongFiles> GetSongsInCategory(string category)
    {
        List<SongFiles> result = new List<SongFiles>();
        
        // Special case for "all" category - only include explicitly categorized songs
        if (category.ToLower() == "all")
        {
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                string songCategory = GetSongCategory((int)song);
                // Only include song if it has a recognized category (not "Unknown")
                if ((int)song != -1 && songCategory != "Unknown") 
                    result.Add(song);
            }
            return result;
        }
        
        // Regular category filtering
        foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
        {
            // Only add songs that match the requested category exactly
            if (GetSongCategory((int)song).ToLower() == category.ToLower())
            {
                result.Add(song);
            }
        }
        
        Debug.Log($"MusicChanger: Found {result.Count} songs in category '{category}'");
        return result;
    }
    
    // Helper method to get songs from multiple categories
    private static List<SongFiles> GetSongsInMultipleCategories(List<string> categories)
    {
        if (categories == null || categories.Count == 0)
        {
            return new List<SongFiles>();
        }
        
        HashSet<int> uniqueSongIds = new HashSet<int>();
        List<SongFiles> result = new List<SongFiles>();
        
        // Special case for "all" category
        if (categories.Contains("all"))
        {
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                if ((int)song != -1) // Skip song_none for regular shuffling
                    result.Add(song);
            }
            return result;
        }
        
        // Add songs from each specified category
        foreach (string category in categories)
        {
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                string songCategory = GetSongCategory((int)song);
                if (songCategory.ToLower() == category.ToLower())
                {
                    // Only add if not already in the result
                    int songId = (int)song;
                    if (!uniqueSongIds.Contains(songId))
                    {
                        uniqueSongIds.Add(songId);
                        result.Add(song);
                    }
                }
            }
        }
        
        Debug.Log($"MusicChanger: Found {result.Count} unique songs in categories: {string.Join(", ", categories.ToArray())}");
        return result;
    }

    private static string ChangeMusic(string[] args)
    {
        if (args.Length == 0)
        {
            string mode = shuffleMode ? " (Shuffle Mode Active" : "";
            if (shuffleMode)
            {
                if (shuffleCategories != null && shuffleCategories.Count > 0 && !shuffleCategories.Contains("all"))
                {
                    mode += $" - Categories: {string.Join(", ", shuffleCategories.ToArray())}";
                }
                else if (shuffleCategoryFilter != "all")
                {
                    // For backward compatibility
                    mode += $" - Category: {shuffleCategoryFilter}";
                }
            }
            mode += ")";
            return $"Usage: song <trackNumber/random/shuffle/default/category>\nOr: song shuffle <category1> <category2> ...\n{mode}\nCategories: all, world, dungeon, battle, misc";
        }

        // Handle "song shuffle category1 category2..." command pattern
        if (args.Length >= 2 && args[0].ToLower() == "shuffle")
        {
            List<string> validCategories = new List<string>();
            
            // Check for "all" which overrides everything else
            bool hasAllCategory = false;
            for (int i = 1; i < args.Length; i++)
            {
                if (args[i].ToLower() == "all")
                {
                    hasAllCategory = true;
                    break;
                }
            }
            
            if (hasAllCategory)
            {
                validCategories.Add("all");
            }
            else
            {
                // Process all category arguments
                for (int i = 1; i < args.Length; i++)
                {
                    string categoryArg = args[i].ToLower();
                    if (categoryArg == "world" || categoryArg == "dungeon" || 
                        categoryArg == "battle" || categoryArg == "misc" || categoryArg == "off")
                    {
                        if (!validCategories.Contains(categoryArg))
                        {
                            validCategories.Add(categoryArg);
                        }
                    }
                    else
                    {
                        return $"MusicChanger: Invalid category '{categoryArg}'. Available categories: all, world, dungeon, battle, misc, off";
                    }
                }
            }
            
            if (validCategories.Count > 0)
            {
                shuffleMode = true;
                shuffleCategories = validCategories; // Set the categories to shuffle
                
                // For backward compatibility, also set the single category filter if only one category
                if (validCategories.Count == 1 && validCategories[0] != "all")
                {
                    shuffleCategoryFilter = validCategories[0];
                }
                else
                {
                    shuffleCategoryFilter = "all"; // Reset single category filter when using multiple
                }
                
                currentSongPlayCount = 0;
                songsSinceLastSilence = 0;
                
                try
                {
                    // Select a random song from these categories
                    List<SongFiles> categorySongs = GetSongsInMultipleCategories(validCategories);
                    if (categorySongs == null || categorySongs.Count == 0)
                    {
                        return $"MusicChanger: No songs found in specified categories.";
                    }
                    
                    SongFiles selectedSong = categorySongs[random.Next(categorySongs.Count)];
                    SetupNewSong(selectedSong);
                    string categoriesStr = string.Join(", ", validCategories.ToArray());
                    return $"MusicChanger: Shuffle mode enabled for categories: {categoriesStr}, starting with {selectedSong}.";
                }
                catch (Exception ex)
                {
                    Debug.LogError($"MusicChanger: Error setting up multi-category shuffle: {ex.Message}");
                    return $"MusicChanger: Error setting up multi-category shuffle. Check log for details.";
                }
            }
            else
            {
                return "MusicChanger: No valid categories specified. Available categories: all, world, dungeon, battle, misc, off";
            }
        }

        // Handle default mode (alias for resume_default)
        if (args[0].ToLower() == "default")
        {
            ResumeDefaultMusicSystem();
            return "MusicChanger: Resumed default music system.";
        }

        // Handle regular shuffle mode (all categories)
        if (args[0].ToLower() == "shuffle")
        {
            shuffleMode = true;
            shuffleCategoryFilter = "all"; // Set to all categories
            shuffleCategories = new List<string>() { "all" }; // Reset to all categories
            currentSongPlayCount = 0; // Reset counter when entering shuffle mode
            songsSinceLastSilence = 0; // Reset silence counter when entering shuffle mode
            
            // Get all available songs that are explicitly categorized (excluding silence)
            List<SongFiles> allSongs = new List<SongFiles>();
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                // Only include songs that have a recognized category
                string songCategory = GetSongCategory((int)song);
                if ((int)song != -1 && songCategory != "Unknown") 
                    allSongs.Add(song);
            }
            
            if (allSongs.Count > 0)
            {
                // Select a random song
                SongFiles selectedSong = allSongs[random.Next(allSongs.Count)];
                SetupNewSong(selectedSong);
                return $"MusicChanger: Shuffle mode enabled, starting with {selectedSong}.";
            }
            else
            {
                return "MusicChanger: No songs available for shuffle mode.";
            }
        }

        // Handle category selection
        string lowerArg = args[0].ToLower();
        if (lowerArg == "world" || lowerArg == "dungeon" || lowerArg == "battle" || lowerArg == "misc" || lowerArg == "off" )
        {
            // Find all songs in the specified category
            List<SongFiles> categorySongs = GetSongsInCategory(lowerArg);
            
            if (categorySongs.Count == 0)
            {
                return $"MusicChanger: No songs found in category '{lowerArg}'.";
            }
            
            // Pick a random song from this category
            SongFiles selectedSong = categorySongs[random.Next(categorySongs.Count)];
            SetupNewSong(selectedSong);
            return $"MusicChanger: Now playing {selectedSong} from category '{lowerArg}'.";
        }

        // Keep track of current shuffle state - don't disable it
        int selectedTrack;

        // If "random" is passed, pick a random track
        if (lowerArg == "random")
        {
            // Get all available songs that are explicitly categorized (excluding silence)
            List<SongFiles> allSongs = new List<SongFiles>();
            foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
            {
                // Only include songs that have a recognized category
                string songCategory = GetSongCategory((int)song); 
                if ((int)song != -1 && songCategory != "Unknown")
                    allSongs.Add(song);
            }
            
            if (allSongs.Count > 0)
            {
                // Select a random song
                SongFiles selectedSong = allSongs[random.Next(allSongs.Count)];
                SetupNewSong(selectedSong);
                return $"MusicChanger: Now playing random track {selectedSong}.";
            }
            else
            {
                return "MusicChanger: No songs available for random selection.";
            }
        }
        else
        {
            // Ensure input is a number
            if (!int.TryParse(args[0], out selectedTrack))
            {
                return "MusicChanger: Invalid track number or category. Use a numeric track ID, 'random', 'shuffle', or a category (world, dungeon, battle, misc, off).";
            }
        }

        // Check if the track number is valid
        if (!Enum.IsDefined(typeof(SongFiles), selectedTrack))
        {
            return $"MusicChanger: Track number {selectedTrack} is not valid.";
        }

        // Set up the selected song and reset play count
        SetupNewSong((SongFiles)selectedTrack);
        currentSongPlayCount = 0; // Reset counter when manually selecting a track
        return $"MusicChanger: Now playing track {selectedTrack} ({(SongFiles)selectedTrack}).";
    }

    // Helper method to get a song's category (used your existing method, but with an int parameter)
    private static string GetSongCategory(int songId)
    {
        // Map song IDs to categories based on JSON
        switch (songId)
        {
            case 1:   // song_02fm
            case 3:   // song_03fm
            case 8:   // song_5strong
            case 10:  // song_06fm
            case 14:  // song_08fm
            case 16:  // song_09fm
            case 27:  // song_16fm
            case 31:  // song_18fm
            case 33:  // song_20fm
            case 35:  // song_21fm
            case 37:  // song_22fm
            case 39:  // song_23fm
            case 41:  // song_25fm
            case 44:  // song_29fm
            case 74:  // song_fcurse
            case 80:  // song_feerie
            case 81:  // song_fgood
            case 88:  // song_fm_rain
            case 91:  // song_fm_swim2
            case 92:  // song_fmover_c
            case 93:  // song_fmover_s
            case 94:  // song_fmsneak2
            case 95:  // song_fneut
            case 99:  // song_fpalac
            case 100: // song_fruins
            case 103: // song_gbad
            case 104: // song_gcurse
            case 110: // song_geerie
            case 111: // song_ggood
            case 112: // song_gmage_3
            case 118: // song_gsnow__b
            case 119: // song_gsunny2
            case 120: // song_magic_2
            case 121: // song_overcast
            case 125: // song_sneaking
            case 127: // song_snowing
            case 130: // song_swimming
                return "World";
                
            case 5:   // song_04fm
            case 7:   // song_05fm
            case 12:  // song_07fm
            case 17:  // song_10
            case 19:  // song_11fm
            case 42:  // song_28
            case 47:  // song_d1
            case 50:  // song_d1fm
            case 52:  // song_d2fm
            case 54:  // song_d3fm
            case 56:  // song_d4fm
            case 58:  // song_d5fm
            case 60:  // song_d6fm
            case 62:  // song_d7fm
            case 64:  // song_d8fm
            case 66:  // song_d9fm
            case 67:  // song_dungeon
            case 68:  // song_dungeon5
            case 69:  // song_dungeon6
            case 70:  // song_dungeon7
            case 71:  // song_dungeon8
            case 72:  // song_dungeon9
            case 76:  // song_fdngn10
            case 77:  // song_fdngn11
            case 78:  // song_fdungn4
            case 79:  // song_fdungn9
            case 82:  // song_fm_dngn1
            case 83:  // song_fm_dngn2
            case 84:  // song_fm_dngn3
            case 85:  // song_fm_dngn4
            case 86:  // song_fm_dngn5
            case 87:  // song_fm_nite3
            case 106: // song_gdngn10
            case 107: // song_gdngn11
            case 108: // song_gdungn4
            case 109: // song_gdungn9
                return "Dungeon";
                
            case 25:  // song_15fm
            case 29:  // song_17fm
            case 46:  // song_30fm
            case 75:  // song_fday___d
            case 105: // song_gday___d
                return "Battle";
            
            case 49:  // song_d10fm
            case 73:  // song_fbad
            case 89:  // song_fm_sqr_2
            case 96:  // song_folk1
            case 97:  // song_folk2
            case 98:  // song_folk3
            case 101: // song_fsneak2
            case 116: // song_gshop
            case 131: // song_tavern  
                return "Misc";
            
            case -1:  // song_none
                return "Off";
                
            default:
                return "Unknown"; // Songs not explicitly categorized should not be included in any category
        }
    }

    private static void SetupNewSong(SongFiles songFile)
    {
        // Get the SongPlayer instance
        DaggerfallSongPlayer songPlayer = GameObject.FindObjectOfType<DaggerfallSongPlayer>();
        if (songPlayer == null)
        {
            Debug.LogError("MusicChanger: Error - DaggerfallSongPlayer not found.");
            return;
        }

        // Find and disable SongManager
        if (originalSongManager == null)
        {
            originalSongManager = GameObject.FindObjectOfType<SongManager>();
        }
        
        if (originalSongManager != null)
        {
            originalSongManager.enabled = false;
            Debug.Log("MusicChanger: Disabled SongManager for custom music playback");
        }

        // Update the current song 
        currentSong = songFile;
        
        // Check specifically for the "None" track
        if ((int)songFile == -1)
        {
            Debug.Log("MusicChanger: Starting 'None' track - treating as 1 minute of silence");
            isSilenceTrack = true;
            silenceTimer = 0f;
            
            // Try more aggressive methods to ensure silence
            songPlayer.Stop();
            
            // Force silence by setting song to None
            songPlayer.Song = SongFiles.song_none;
            
            // Try to access audio source to mute it directly
            var audioSource = songPlayer.GetComponent<AudioSource>();
            if (audioSource != null)
            {
                Debug.Log("MusicChanger: Setting AudioSource volume to 0 for silence");
                audioSource.volume = 0f;
            }
            else
            {
                Debug.Log("MusicChanger: WARNING - Could not find AudioSource to mute");
            }
            
            Debug.Log("MusicChanger: Stopped currently playing song for silence track");
        }
        else
        {
            isSilenceTrack = false;
            songPlayer.Song = songFile;
            Debug.Log($"MusicChanger: Setting up new song {songFile} (ID: {(int)songFile}) - Category: {GetSongCategory((int)songFile)}");
            
            // If coming from silence, restore audio
            var audioSource = songPlayer.GetComponent<AudioSource>();
            if (audioSource != null)
            {
                audioSource.volume = 1.0f;
                Debug.Log("MusicChanger: Restored AudioSource volume to 1.0");
            }
            
            songPlayer.Play(songFile);
        }
        
        // Record the time when we start playing a song
        lastSongStartTime = Time.time;
        
        // Always reset the play count when setting up a new song
        currentSongPlayCount = 0;
    }

    private static string ResumeDefaultMusic(string[] args)
    {
        ResumeDefaultMusicSystem();
        return "MusicChanger: Resumed default music system.";
    }

    private static void ResumeDefaultMusicSystem()
    {
        currentSong = null;
        shuffleMode = false;
        currentSongPlayCount = 0;
        isSilenceTrack = false;
        songsSinceLastSilence = 0;
        shuffleCategoryFilter = "all"; // Reset to default
        shuffleCategories = new List<string>() { "all" }; // Reset multi-category list

        if (originalSongManager != null)
        {
            originalSongManager.enabled = true;
            Debug.Log("MusicChanger: Resumed default music system");
        }
    }
}