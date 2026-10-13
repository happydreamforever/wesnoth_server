# Complete the first offline turn

Windows APK packaging, signing, installation, complete OBB import and the visible main menu now pass. The user confirms that they have not played a turn yet. Use the game already open in LDPlayer; this test needs no pull, build, reinstall or server command. Keep the installed app and all completed build/data stages.

1. Disconnect internet for this local test, leaving LDPlayer running.
2. From the main menu choose **Campaigns**.
3. Select **Heir to the Throne, Classic**. Choose **Fighter / Easy**, then **Play**. This is the Classic campaign; the newer campaign has a similar name.
4. Answer **Yes** to **Play Battle Training?**, then choose either hero.
5. Follow the instructions to select/move your hero and attack the training dummy.
6. When prompted, press **End Turn** at the bottom right. Wait for the dummy's turn and confirm that control returns on **turn 2** (the healing lesson).

The exact gamedata-1.19.26 version puts this tutorial inside the Classic campaign; its title screen has no separate Tutorial button. End Turn is intentionally disabled until the movement and first attack lessons are completed.

Expected result: the map, terrain, units and text render; unit selection/movement/attack respond; the AI takes its turn; turn 2 begins without a crash. Also note whether music or sound effects are audible. This establishes the first local playable turn; it does not yet establish the client/server LAN game.

Report:

- Did the training map open, and were the map/text readable?
- Did movement and attack work, and did turn 2 begin?
- Was music or sound audible, and was internet disconnected?
- If anything failed, the last successful action and exact visible error or screen state.

On a successful manual test, a short written result is enough. On failure, report what happened before rerunning the APK installer or changing build files. The previous successful startup logs are retained under diagnostics/game-20261013-141502-308-32ac9f66ce3741e4a0ca9f94f46e35a9.txt, game-logcat-20261013-144318-475-da8d4905c22944da8f5a9a3464550cf1.txt and game-userdata-20261013-144318-661-da8d4905c22944da8f5a9a3464550cf1. New gameplay errors may require a fresh scoped log capture; the saved startup logs do not automatically include later play.

After the local turn is confirmed, the next checkpoint connects this Android game to the existing Windows server and completes a LAN turn without internet. Phone testing, MongoDB integration and custom game features remain subsequent required work. For the later server launch use the recorded current MSYS2 root explicitly, because the existing launcher still defaults to the historical D:\Test\msys64 path; no global default or runtime changes are requested now.
