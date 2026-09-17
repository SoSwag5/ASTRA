# Endpoint inventory

Statically extracted decorator paths; router prefixes must be composed from APIRouter definitions. main.py mounts all private routers behind the common guard.

Router prefixes: `campaign.py` → `/api/campaign`, `privacy.py` → `/api/privacy`,
`recall_api.py` → `/api/recall`, `search_workspace.py` → `/api/search`,
`source_catalog.py` → `/api/search`, `gmail_api.py` → `/api/gmail`.

`gmail_api.py` (issue #44) is the Gmail OAuth credential layer. `{slug}` is
validated against a fixed two-value slot map (`primary`/`secondary`); it is
the only caller input, and a caller cannot select a Google endpoint, a scope,
a callback host, a client ID or a credential key. State changes are POST;
no response carries a token field. `secondary` is gated and returns
`SECONDARY_NOT_ENABLED` (OD-012). See `docs/architecture/GMAIL_OAUTH.md`.

| Module | Method | Decorator path | Handler |
|---|---|---|---|
| campaign.py | GET |  | overview |
| campaign.py | PUT | /settings | save_settings |
| campaign.py | POST | /jobs/{job_id}/track | track |
| campaign.py | POST | /jobs/{job_id}/seen | seen |
| campaign.py | POST | /backup | backup |
| campaign.py | GET | /windows-schedule | get_windows_schedule |
| campaign.py | POST | /windows-schedule | set_windows_schedule |
| gmail_api.py | GET | /status | gmail_status |
| gmail_api.py | POST | /accounts/{slug}/authorize | start_authorization |
| gmail_api.py | GET | /accounts/{slug}/authorize | authorization_status |
| gmail_api.py | POST | /accounts/{slug}/authorize/cancel | cancel_authorization |
| gmail_api.py | POST | /accounts/{slug}/disconnect | disconnect_account |
| main.py | GET | /api/health | health |
| main.py | GET | /api/dashboard | dashboard |
| main.py | GET | /api/profile | profile |
| main.py | PUT | /api/profile | update_profile |
| main.py | POST | /api/import/cv | cv_upload |
| main.py | PUT | /api/profile/facts/{kind}/{fact_id} | correct_fact |
| main.py | POST | /api/import/tracker | tracker_upload |
| main.py | POST | /api/import/csv | csv_upload |
| main.py | GET | /api/jobs | jobs |
| main.py | POST | /api/jobs | create_job |
| main.py | POST | /api/import/url | import_url |
| main.py | GET | /api/jobs/{id} | job_detail |
| main.py | POST | /api/jobs/{id}/{action} | job_action |
| main.py | POST | /api/bulk/prepare | bulk |
| main.py | GET | /api/records/{kind} | records |
| main.py | POST | /api/records/{kind} | save_record |
| main.py | GET | /api/career-tracks | career_tracks_list |
| main.py | GET | /api/profile/career-suggestions | career_suggestions |
| main.py | POST | /api/settings/career-focus | set_career_focus |
| main.py | GET | /api/settings | get_settings |
| main.py | PUT | /api/settings | put_settings |
| main.py | POST | /api/sync | sync |
| main.py | POST | /api/tasks/{name} | run_task |
| main.py | POST | /api/browser/test | test_browser |
| main.py | POST | /api/browser/rehearsal | test_rehearsal |
| main.py | GET | /api/files/{path:path} | file_download |
| main.py | GET | /demo | demo_page |
| privacy.py | GET |  | privacy_info |
| privacy.py | GET | /export | export_data |
| privacy.py | POST | /delete | delete_data |
| privacy.py | PUT | /credentials/openai | save_credential |
| privacy.py | PUT | /application-profile | save_application_profile |
| privacy.py | GET | /self-check | self_check |
| privacy.py | GET | /security-events | security_events |
| privacy.py | GET | /ai-usage | ai_usage |
| privacy.py | GET | /market/{country} | market_policy |
| recall_api.py | GET |  | overview |
| recall_api.py | GET | /audit/{run_id} | audit |
| recall_api.py | PUT | /policy | policy |
| recall_api.py | POST | /jobs/{job_id}/feedback | feedback |
| recall_api.py | POST | /paste-preview | paste_preview |
| recall_api.py | PUT | /jobs/{job_id}/source | preferred_source |
| search_workspace.py | GET | /overview | overview |
| search_workspace.py | GET | /telemetry | telemetry_latest |
| search_workspace.py | GET | /telemetry/runs | telemetry_history |
| search_workspace.py | GET | /telemetry/runs/{run_id} | telemetry_run |
| search_workspace.py | POST | /scan | scan |
| search_workspace.py | POST | /sources | add_source |
| search_workspace.py | POST | /jobs/{job_id}/notes | notes |
| search_workspace.py | POST | /jobs/{job_id}/save | save_job |
| search_workspace.py | GET | /tracking | tracking |
| search_workspace.py | POST | /tracking/{app_id}/followup | save_followup |
| source_catalog.py | GET | /portals | portals |
| source_catalog.py | POST | /portals/{source_id}/checked | checked |
| source_catalog.py | POST | /portals | add_portal |
| source_catalog.py | PUT | /portals/{source_id} | configure_portal |

## Issue #45 Gmail evidence routes

All inherit the existing private API guard and no-store response policy.

| Module | Method | Route | Handler |
|---|---|---|---|
| gmail_api.py | GET | /api/gmail/sync/status | sync_status |
| gmail_api.py | GET | /api/gmail/confirmations | confirmations |
| gmail_api.py | POST | /api/gmail/accounts/{slug}/sync | synchronize |
