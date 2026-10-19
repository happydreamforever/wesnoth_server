# Next step: check the unidentified executable code with Windows Security

The supplied caller-region report passed all 13 queries and both identity checks. Every queried address is currently `MEM_COMMIT`, `MEM_PRIVATE`, `PAGE_EXECUTE_READ`, with allocation base `0x10000000`. This places the recorded caller addresses in private executable memory at collection time; it does not identify its author or prove it is malicious. These are current mappings, not a reconstruction of the earlier capture.

The helper deliberately skips mapped-filename lookup for private memory, so `not_applicable` is not a failed filename query or proof of a fileless origin. Repeating module inventories or the same region collector will not establish the missing identity. The prior scratch trace identifies the conflicting file opener; the real earlier MongoDB-crash holder was not directly captured.

## One practical Windows check

A Windows Security **Quick scan** checks processes, memory and startup locations. Microsoft recommends it for on-demand scans. [Microsoft scan guidance](https://learn.microsoft.com/en-us/defender-endpoint/schedule-antivirus-scans)

Before starting, save the existing Process Monitor capture locally if it has not been saved: **File -> Save**, choose native **PML** format and an unused filename such as `D:\Test\mongo-blocker-before-scan.pml`. Keep it on Windows; do not upload the full PML. Preserve the already supplied reports and original MongoDB runtime. **The antivirus scan may quarantine or otherwise remediate detected threats; it is not a read-only diagnostic.**

1. Open **Start -> Windows Security -> Virus & threat protection**.
2. Select **Quick scan** and let it finish. Use the installed protection; no Git pull, package installation, collector rerun or manual reboot is requested.
3. Send the completed scan result. For detections, open **Protection history** and return the **threat name, affected item and action/status**. A screenshot or pasted text is sufficient; do not upload suspected binaries or memory dumps.
4. If Quick scan is unavailable, another antivirus provider is shown, protection is disabled, or an error appears, send that displayed message/provider name. Do not force-enable/disable security settings or install another scanner for this step.

[Microsoft documents these Windows Security controls](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-security-center-antivirus). A clean scan would not prove the unknown code is legitimate or the sharing conflict fixed. A threat detection must also be assessed for relevance; an unrelated detection would not establish the real MongoDB crash cause.

Keep MongoDB stopped for now. Do not kill svchost processes, alter NetActvity, delete system DLLs or repair/delete WiredTiger files based only on these metadata results. No Defender exclusions, memory dump, new code modification, database startup or game rebuild is requested. Local MongoDB initialization, admin setup and offline Alliance validation remain pending.
