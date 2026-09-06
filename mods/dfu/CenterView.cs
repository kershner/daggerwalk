using UnityEngine;
using DaggerfallWorkshop.Game;
using DaggerfallWorkshop.Game.Utility.ModSupport;

// Restores DFU's orphaned "Center View" action. The action is exposed in the
// controls menu and defaults to Home, but DFU 1.1.1 never applies it to the
// player camera.
[DisallowMultipleComponent]
public class CenterView : MonoBehaviour
{
    public static Mod mod;

    [Invoke(StateManager.StateTypes.Start, 0)]
    public static void Init(InitParams initParams)
    {
        mod = initParams.Mod;

        GameObject oldObject = GameObject.Find(mod.Title);
        if (oldObject != null)
            Object.Destroy(oldObject);

        GameObject go = new GameObject(mod.Title);
        Object.DontDestroyOnLoad(go);
        go.AddComponent<CenterView>();

        mod.IsReady = true;
        Debug.Log("[CenterView] Ready.");
    }

    private void Update()
    {
        InputManager inputManager = InputManager.Instance;
        if (inputManager == null ||
            !inputManager.ActionStarted(InputManager.Actions.CenterView))
        {
            return;
        }

        PlayerMouseLook mouseLook = GameManager.Instance.PlayerMouseLook;
        if (mouseLook == null)
            return;

        // Level the vertical view without changing the player's heading.
        // SetFacing() also synchronizes DFU's smoothed current/target angles,
        // preventing the old pitch from being restored on the next frame.
        mouseLook.SetFacing(mouseLook.Yaw, 0f);
    }
}
