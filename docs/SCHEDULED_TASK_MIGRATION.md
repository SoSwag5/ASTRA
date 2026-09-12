# Discovery task naming

New installations use **ASTRA Local Discovery**. Existing installations retain
**Ayham Job Hunter - Local Discovery** until deliberately migrated. The scheduler
script detects the old name and continues to manage that task in place. It refuses
to manage two simultaneous tasks or a task pointing at another installation.
No live task was modified by this release-closure pass.

Renaming only script strings can leave an orphan task or two independent scanners.
Although the process lock reduces overlap, duplicate schedules are not supported.

To migrate later, with explicit operator approval:

1. Inspect the old task in Windows Task Scheduler. Confirm its Python executable,
   discovery script and working directory point at this installation. Record its
   interval, enabled state, user and settings; export its XML as a local backup.
2. Wait for any scan to finish. Disable the old task, then remove that exact old
   task. Do not delete tasks belonging to another installation.
3. Use ASTRA's scheduled-discovery control to Enable at the recorded interval.
   With no legacy task present this registers **ASTRA Local Discovery**.
4. Confirm only the new task exists, it runs as the current limited user, does not
   wake the computer, and points at the same installation. Restore the previous
   disabled state if discovery was previously disabled.
5. Run one deliberate discovery check if desired; inspect its result. If rollback
   is needed, remove the new task before importing the saved old task XML.

Do not perform this migration while another process is scanning or updating ASTRA.
