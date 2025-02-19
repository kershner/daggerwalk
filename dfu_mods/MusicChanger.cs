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
    
    // Timer related variables
    private static float inactivityTimer = 0f;
    private static float inactivityThreshold = 600f; // 10 minutes

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
                    ResetInactivityTimer();
                    return;
                }

                // Check if song has stopped
                if (!songPlayer.IsPlaying)
                {
                    if (shuffleMode)
                    {
                        currentSongPlayCount++;
                        
                        // Only pick a new song if we've played the current one enough times
                        if (currentSongPlayCount >= shuffleRepeatsPerSong)
                        {
                            // Pick a new random song
                            Array songValues = Enum.GetValues(typeof(SongFiles));
                            int newTrack;
                            do
                            {
                                newTrack = (int)songValues.GetValue(random.Next(songValues.Length));
                            } while (newTrack == (int)currentSong && songValues.Length > 1); // Avoid same song if possible
                            
                            currentSong = (SongFiles)newTrack;
                            currentSongPlayCount = 0; // Reset counter for new song
                            Debug.Log($"MusicChanger: Shuffle mode - Playing new random track {currentSong.Value}");
                        }
                        else
                        {
                            Debug.Log($"MusicChanger: Shuffle mode - Replaying current track (play {currentSongPlayCount + 1} of {shuffleRepeatsPerSong})");
                        }
                    }
                    
                    songPlayer.Song = currentSong.Value;
                    songPlayer.Play(currentSong.Value);
                }

                // Update inactivity timer - only if not in shuffle mode
                if (!shuffleMode)
                {
                    inactivityTimer += Time.deltaTime;
                    if (inactivityTimer >= inactivityThreshold)
                    {
                        Debug.Log("MusicChanger: Inactivity threshold reached, resuming default music");
                        ResumeDefaultMusicSystem();
                        ResetInactivityTimer();
                    }
                }
            }
        }
    }

    private static void ResetInactivityTimer()
    {
        inactivityTimer = 0f;
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
            ResetInactivityTimer();
            return "MusicChanger: Resumed default music system.";
        }

        // Handle shuffle mode
        if (args[0].ToLower() == "shuffle")
        {
            shuffleMode = true;
            currentSongPlayCount = 0; // Reset counter when entering shuffle mode
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

        // Set up the selected song
        SetupNewSong((SongFiles)selectedTrack);
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
        songPlayer.Song = songFile;
        songPlayer.Play(songFile);

        // Reset the inactivity timer when a new song is requested
        ResetInactivityTimer();
    }

    private static string ResumeDefaultMusic(string[] args)
    {
        ResumeDefaultMusicSystem();
        ResetInactivityTimer();
        return "MusicChanger: Resumed default music system.";
    }

    private static void ResumeDefaultMusicSystem()
    {
        currentSong = null;
        shuffleMode = false;
        currentSongPlayCount = 0;

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