using System;
using UnityEngine;
using DaggerfallWorkshop;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;

public class AutoWalk : MonoBehaviour
{
    public static Mod mod;
    private bool autoWalk = false;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;
        mod.IsReady = true;

        var go = new GameObject(mod.Title);
        go.AddComponent<AutoWalk>();
    }

    void Update()
    {
        var inputManager = InputManager.Instance;
        var playerMotor = GameManager.Instance?.PlayerMotor;
        var speedChanger = playerMotor?.GetComponent<PlayerSpeedChanger>();

        if (inputManager == null || playerMotor == null || speedChanger == null || !GameManager.Instance.TransportManager.IsOnFoot)
            return;

        // Toggle Auto-Walk with "\"
        if (Input.GetKeyDown(KeyCode.Backslash))
        {
            ToggleAutoWalk(inputManager);
        }

        // Disable auto-walk if 'back' (S) is pressed
        if (autoWalk && inputManager.HasAction(InputManager.Actions.MoveBackwards))
        {
            ToggleAutoWalk(inputManager);
        }

        if (autoWalk)
        {
            // Explicitly add MoveForwards action each frame
            inputManager.AddAction(InputManager.Actions.MoveForwards);
            
            // Ensure walking speed
            speedChanger.isRunning = false;
            
            // Additional attempt to force movement
            inputManager.ToggleAutorun = true;
        }
    }

    private void ToggleAutoWalk(InputManager inputManager)
    {
        autoWalk = !autoWalk;
        Debug.Log($"AutoWalk: {(autoWalk ? "Enabled" : "Disabled")}");
        
        if (autoWalk)
        {
            inputManager.AddAction(InputManager.Actions.MoveForwards);
        }
        else
        {
            // Clear all current actions
            inputManager.ClearAllActions();
            inputManager.ToggleAutorun = false;
        }
    }
}