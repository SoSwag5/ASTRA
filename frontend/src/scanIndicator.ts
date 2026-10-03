/**
 * The shell's "Scanning…" label follows the real scan controller only.
 * `running` from the overview is a generic work lock (maintenance, startup
 * housekeeping) and is not a scan.
 */
export const scanIsActive = (status: {active?: unknown} | null | undefined): boolean => !!status?.active;
