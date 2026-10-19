# Next step: quarantine the reported threat and return its status

The expanded user report identifies **C:\Windows\SysWOW64\netactive32.dll** as the affected item for **Trojan:Win32/Wacatac.B!ml**, **Severe**, **Active**, dated **10/19/2026 3:36 PM**. The affected filename is now known. Network disconnection, remediation outcome and final scan completion have not been confirmed. This alert does not establish a relationship to NetActvity/PID4600 or the cause of the earlier MongoDB crash.

## Immediate Windows action

1. If Windows is connected, disconnect its network connections for now, including Ethernet/Wi-Fi. Keep MongoDB stopped and leave builds/Git pulls until the threat state is reviewed.
2. Open **Windows Security -> Virus & threat protection -> Protection history** and expand this detection. Choose **Actions -> Quarantine**, then **Start actions** if that button is shown. Let Defender complete the action. Do not select Allow on device, Restore, or an antivirus exclusion, and do not manually delete the DLL. [Microsoft Protection History guidance](https://support.microsoft.com/en-us/windows/security/windows-security/protection-history-in-the-windows-security-app)
3. Return the action taken and the **resulting status**. Expected containment confirmation is a Defender status such as **Threat quarantined** or **Threat blocked**; this is not proof that the whole computer is clean. If it remains Active, reports Remediation incomplete, requests a restart, or the stated controls are unavailable, send the exact displayed status/options.

If quarantine has already completed, report that outcome instead of repeating it. Do not send the detected binary, full PML or a memory dump, and do not delay quarantine for further diagnostic collection. Existing capture/reports stay on Windows; do not restore any quarantined item to reproduce the file-locking failure.

## Project scope

The prior scratch trace and current private executable-region report remain valid but do not attribute their caller code to this DLL. No successful cleanup, credential theft or specific malware-family behavior is inferred. The active alert takes priority over database experiments. No new collector, pull, build, install, manual service/process change, database repair or startup is requested. The next check depends on Defender's remediation outcome; do not restart the historical Git/registry/reboot investigation.
