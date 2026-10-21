# Next test: find Koichi in Yama and check the personal leader

The user confirms all requested results from the separate **My team** lookup: Koichi's saved ID and team values match. The confirmation includes keeping WAN disconnected and local Ethernet connected. Creation and later own-team retrieval are accepted at user-observed scope; neither proves team persistence after a restart.

Keep the current UniPlayer session and all three Windows backend windows (MongoDB, admin service and account bridge) running. Keep WAN disconnected and local Ethernet connected. Use the installed app; no PowerShell command or new delivery is needed.

## 1. Find the team through its area

1. Press **OK** on the My team details dialog to return to the Teams menu.
2. Select **Browse areas and teams**, then press **Open**.
3. Select **Yama**, then press **Open**.
4. Select the **Koichi — team level 1, 1/8 members** row, then press **Open**.
5. Expect the same details:

| Field | Expected value |
| --- | --- |
| Team | Koichi |
| Team ID | `4cd736d3-dc6c-4c3d-a816-e7682b56db30` |
| Area | Yama |
| Area ID | `ff010e4d-af74-4906-8ba6-5f096aaf90ec` |
| Team level / experience / rating | 1 / 0 / 1000 |
| Members | 1/8 |
| Roster | UniPlayer (captain) — Spearman, leader level 1 |

If the list has more than one page, select **More areas** or **More teams** and press **Open** to reach the next page; **Previous page** returns to the preceding page. If the team is absent after checking the available pages, or an error appears, send the exact result and stop. Preserve the existing team rather than creating another.

## 2. Check the personal leader

1. Press **OK** on the team details.
2. Press **Back** from the team list, then **Back** from the area list, then **Back** from the Teams menu. This returns to the Alliance menu.
3. Select **View personal leader** and press **Open**.
4. Expect the same player ID, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**.

**Stop at the personal-leader dialog.** Return whether Koichi appeared under Yama with the same team ID/roster, whether the player/leader/experience values match, and whether WAN stayed disconnected. This checks the public directory/detail path and that team creation did not change the personal leader's displayed experience. It does not create a team, award XP or test a battle.

After this result, team persistence across a controlled restart remains to be checked; the accepted account-only restart test predates Koichi. Joining teams, captain management, custom campaign rewards and team battles remain later implementation slices. Preserve the installed APK, OBB/data, trusted profile, server identity, runtime and build backups. Keep passwords, session tokens and private runtime files private.
