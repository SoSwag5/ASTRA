# Local access and browser sessions

ASTRA is a Windows local workspace. Non-loopback peers, untrusted Host/Origin,
cross-site requests and browser resource/navigation requests to private APIs are
rejected by the backend. Those controls do not identify an OS user.

In default keyless mode, local processes — including other local users on a
shared machine — may call the API. This is an **accepted architectural residual
risk (R-15)**: ASTRA's supported trust boundary is the local OS user account /
localhost environment, and it implements no application identities or inter-user
authorization, so ASVS 5.0.0 8.2.1/8.2.2 are N/A by architecture rather than a
met control. Do **not** describe this mode as authenticated or as suitable for a
shared or untrusted computer; use the optional protected mode below on any
multi-user host. No live configuration was changed in this pass.

## Optional protected mode

`APP_TOKEN` is an installation access key configured locally, not an account
password database or a browser session identifier. Use a cryptographically random
key (at least 32 random bytes encoded as text, at most 1,000 characters); keep its
configuration file protected by the OS. Do not share it or put it in a URL.
Changing it requires restarting the server. Missing or compromised keys require
local operator rotation; there is no remote password recovery mechanism.

The browser asks for the key before loading private data. `POST /api/access`
verifies the key exactly and issues a CSPRNG 256-bit reference token. Private API
requests accept that token, not the static key. New tokens remain in memory;
legacy sessionStorage credentials are removed on page load. The server stores
only SHA-256 token digests, creation and last-use times. Session memory is bounded
to 16 entries; oldest activity is evicted on overflow.

Five failed exchange attempts are allowed per process-wide 60-second rolling
window. Further attempts return 429 and Retry-After before key comparison.
Blocked attempts do not extend the window; there is no persistent/permanent
account lock. A sustained local attacker can still cause temporary access delays.
Rate limits reset at process restart; a process able to restart the app is inside
the trusted local administration boundary. A random key is still essential.

Backend sessions expire after 15 minutes without API activity or eight hours
absolute age. The browser additionally closes after 15 minutes without keyboard
or pointer interaction and at eight hours. Restart or key rotation invalidates
all references. Reauthentication creates a new token and revokes the presented
previous token. No cookies, JWT claims, user accounts, roles or account deletion
mechanism is implemented.

## Closing and reconnecting

Close workspace immediately unmounts the private UI, clears key/token memory,
aborts pending fetches and revokes tracked download blob URLs. Pagehide, offline
events, expired/invalid-session responses and BFCache restoration also close the
workspace. A failed API connection is detected on the next request, including the
20-second status poll. On protected installations, opening again requires the
key. On keyless installations this is a privacy screen, not authentication.

The client requests server revocation when possible; if offline, local cleanup
still occurs and the server reference expires at its normal deadline. Closing a
browser tab is not a guarantee of remote delivery. Files explicitly exported or
opened in a separate download window remain under the user's control. Server-side
scheduled work can continue after the tab closes.

Tests: `tests/security/test_access_sessions.py`, `test_closure_boundary.py`, and
`test_browser_termination.py`. The optional key exchange is a per-installation
protection, not a multi-user access-control system; the single-user local trust
boundary and its shared-host residual are recorded as R-15 in the risk register.
