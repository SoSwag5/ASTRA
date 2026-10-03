/**
 * The shell's "Scanning…" label follows the real scan controller only.
 * `running` from the overview is a generic work lock (maintenance, startup
 * housekeeping) and is not a scan.
 */
export const scanIsActive = (status: {active?: unknown; active_scan?: unknown} | null | undefined): boolean =>
  !!(status && (status.active ?? status.active_scan));
