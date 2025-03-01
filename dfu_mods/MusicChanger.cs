using System;
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
    private static float silenceDuration = 60f; // 1 minute of silence
    private static float silenceTimer = 0f;
    private static int songsSinceLastSilence = 0;
    private static int songsBeforeSilence = 3; // Play silence after every X songs in shuffle mode

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
        ConsoleCommandsDatabase.RegisterCommand("song", "Changes the current music track.", "song <trackNumber/random/shuffle/default>", ChangeMusic);
        ConsoleCommandsDatabase.RegisterCommand("list_music_tracks", "Lists available music tracks.", "list_music_tracks", ListAvailableTracks);
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
            
            // Pick a new random song
            Array songValues = Enum.GetValues(typeof(SongFiles));
            int newTrack;
            do
            {
                newTrack = (int)songValues.GetValue(random.Next(songValues.Length));
            } while (newTrack == (int)currentSong && songValues.Length > 1); // Avoid same song if possible
            
            // Only increment songs since last silence when we're playing a real song (not silence)
            if (!isSilenceTrack && (int)((SongFiles)newTrack) != -1)
            {
                songsSinceLastSilence++;
            }
            else if ((int)((SongFiles)newTrack) == -1)
            {
                // Reset counter if we happen to randomly select silence
                songsSinceLastSilence = 0;
            }
            
            // Set up the selected song (handles both normal songs and silence)
            SetupNewSong((SongFiles)newTrack);
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

    private static string ChangeMusic(string[] args)
    {
        if (args.Length == 0)
        {
            string mode = shuffleMode ? " (Shuffle Mode Active)" : "";
            return $"Usage: song <trackNumber/random/shuffle/default>{mode}";
        }

        // Handle default mode (alias for resume_default)
        if (args[0].ToLower() == "default")
        {
            ResumeDefaultMusicSystem();
            return "MusicChanger: Resumed default music system.";
        }

        // Handle shuffle mode
        if (args[0].ToLower() == "shuffle")
        {
            shuffleMode = true;
            currentSongPlayCount = 0; // Reset counter when entering shuffle mode
            songsSinceLastSilence = 0; // Reset silence counter when entering shuffle mode
            Array songValues = Enum.GetValues(typeof(SongFiles));
            int trackNumber = (int)songValues.GetValue(random.Next(songValues.Length));
            
            // Set up the first song in shuffle mode
            SetupNewSong((SongFiles)trackNumber);
            return "MusicChanger: Shuffle mode enabled, starting with random track.";
        }

        // Keep track of current shuffle state - don't disable it
        int selectedTrack;

        // If "random" is passed, pick a random track
        if (args[0].ToLower() == "random")
        {
            Array songValues = Enum.GetValues(typeof(SongFiles));
            selectedTrack = (int)songValues.GetValue(random.Next(songValues.Length));
        }
        else
        {
            // Ensure input is a number
            if (!int.TryParse(args[0], out selectedTrack))
            {
                return "MusicChanger: Invalid track number. Please enter a numeric track ID, 'random', or 'shuffle'.";
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

        // Update both the current song and the player's Song property
        currentSong = songFile;
        
        // Check specifically for the "None" track
        if ((int)songFile == -1)
        {
            Debug.Log("MusicChanger: Starting 'None' track - treating as 1 minute of silence");
            isSilenceTrack = true;
            silenceTimer = 0f;
            
            // Try more aggressive methods to ensure silence
            songPlayer.Stop();
            
            // Force silence by setting song to None and volume to 0
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
            Debug.Log($"MusicChanger: Setting up new song {songFile} (ID: {(int)songFile})");
            
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

        if (originalSongManager != null)
        {
            originalSongManager.enabled = true;
            Debug.Log("MusicChanger: Resumed default music system");
        }
    }

    private static string ListAvailableTracks(string[] args)
    {
        Debug.Log("MusicChanger: Listing available tracks...");
        string trackList = "Available Tracks:\n";

        foreach (SongFiles song in Enum.GetValues(typeof(SongFiles)))
        {
            int trackID = (int)song;
            string entry = $"{trackID}: {song}\n";
            Debug.Log(entry);
            trackList += entry;
        }

        return trackList;
    }
}