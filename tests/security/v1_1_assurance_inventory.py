"""Issue #48: traceability from every v1.1 negative-test requirement to tests.

Each requirement below is a negative or security test that ADR-0007, ADR-0008,
ADR-0009 or the v1.1 threat-model delta's abuse-case table says must exist
before its control can be relied on in the v1.1 release evidence pack. The
tests named here are the consolidated v1.1 security regression suite.

`tests/conftest.py` marks every listed test, and every test in
`tests/security/test_v1_1_assurance.py`, with `v1_1_assurance`, so the suite
runs with:

    python -m pytest -m v1_1_assurance

`tests/security/test_v1_1_assurance.py` fails if a listed test no longer
exists, if a requirement has no test, or if an abuse case has no requirement.
Entries name a test function; pytest runs every parametrization of it.

This file maps evidence. It does not decide whether a residual risk is
acceptable; only the Owner decides that (see docs/security/RISK_REGISTER.md).
"""

OAUTH = 'tests/test_gmail_oauth.py'
OAUTH_SECRETS = 'tests/security/test_gmail_oauth_secrets.py'
SYNC = 'tests/test_gmail_sync.py'
SYNC_PRIVACY = 'tests/security/test_gmail_sync_privacy.py'
STATE = 'tests/test_application_state.py'
STATE_PRIVACY = 'tests/security/test_application_state_privacy.py'
TRANSPORT = 'tests/test_job_provider_transport.py'
PROVIDERS = 'tests/test_job_providers.py'
ISOLATION = 'tests/test_provider_failure_isolation.py'
REMEDIATION = 'tests/test_provider_remediation.py'
REMEDIATION_2 = 'tests/test_provider_remediation_round2.py'
LEVER = 'tests/test_lever_provider.py'
ASHBY = 'tests/test_ashby_provider.py'
GREENHOUSE = 'tests/test_greenhouse_characterization.py'
DEDUPE = 'tests/test_job_deduplication.py'
CONTROLS = 'tests/security/test_controls.py'
ASSURANCE = 'tests/security/test_v1_1_assurance.py'


def _t(path, *names):
    return [f'{path}::{name}' for name in names]


#: Abuse cases in the order of the threat-model delta's table.
ABUSE_CASES = {
    'TM-1': 'OAuth refresh-token exfiltration via logs, exports or diagnostic bundles',
    'TM-2': 'OAuth refresh-token theft by a local or shared-host actor',
    'TM-3': 'OAuth callback interception, CSRF, code substitution or account mix-up',
    'TM-4': 'Spoofed confirmation email causing a false HIGH-confidence reconciliation',
    'TM-5': 'Malicious HTML or links in email rendered as trusted or auto-followed',
    'TM-6': 'Malformed or oversized email or provider payload exhausting the parser',
    'TM-7': 'SSRF via a provider URL or a link in a posting or email',
    'TM-8': 'Duplicate or reconciliation manipulation forcing a false merge or split',
    'TM-9': 'Status-evidence spoofing claiming a stronger application state',
    'TM-10': 'Future AI email classification treating email content as instructions',
}

#: Abuse cases whose control does not exist because the feature does not
#: exist. They still need a guard test that fails if the feature appears.
NOT_YET_APPLICABLE = {'TM-10'}

REQUIREMENTS = [
    # ---- ADR-0007: Gmail OAuth and credential storage (R-16) -------------
    {'id': 'A7-SCOPE', 'source': 'ADR-0007 Decision: scope', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'Only gmail.readonly is requested; a missing or broader grant is refused before anything is stored.',
     'tests': _t(OAUTH, 'test_authorization_request_asks_for_exactly_gmail_readonly',
                 'test_authorization_request_never_asks_for_a_broader_or_unrelated_scope',
                 'test_a_token_missing_gmail_readonly_is_rejected',
                 'test_a_broader_than_requested_grant_is_rejected',
                 'test_a_broader_grant_stores_nothing_at_all')
              + _t(SYNC, 'test_refresh_scope_mismatch_blocks_before_mailbox')},
    {'id': 'A7-PKCE', 'source': 'ADR-0007 Decision: flow', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'PKCE uses S256 only, with an RFC-conformant verifier sent only to the token endpoint.',
     'tests': _t(OAUTH, 'test_code_verifier_meets_rfc_length_charset_and_entropy',
                 'test_s256_challenge_matches_the_rfc_7636_known_vector',
                 'test_only_s256_is_ever_offered_and_plain_is_never_sent',
                 'test_token_exchange_sends_the_exact_redirect_uri_and_verifier')},
    {'id': 'A7-STATE', 'source': 'ADR-0007 Decision: flow; threat delta TM-3 tests', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'Incorrect, missing, duplicate, replayed, expired, cancelled and superseded callbacks are rejected; concurrent callbacks yield one result.',
     'tests': _t(OAUTH, 'test_state_has_at_least_128_bits_of_entropy_and_is_unique_per_attempt',
                 'test_correct_state_is_accepted_exactly_once',
                 'test_incorrect_state_is_rejected', 'test_missing_state_is_rejected',
                 'test_duplicate_state_parameter_is_rejected',
                 'test_replayed_callback_cannot_trigger_a_second_exchange',
                 'test_expired_attempt_is_rejected', 'test_cancelled_attempt_cannot_complete',
                 'test_a_new_attempt_supersedes_the_previous_one_for_that_slot',
                 'test_concurrent_callbacks_produce_exactly_one_terminal_success',
                 'test_restart_leaves_no_resumable_attempt',
                 'test_a_local_request_without_the_correct_state_cannot_complete_the_flow',
                 'test_adversarial_callback_shapes_are_rejected',
                 'test_a_credential_bearing_callback_parameter_is_refused_outright')},
    {'id': 'A7-LOOPBACK', 'source': 'ADR-0007 Decision: flow', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'The redirect listener binds only to numeric loopback on an ephemeral port and closes after one terminal callback or its deadline.',
     'tests': _t(OAUTH, 'test_listener_binds_only_to_numeric_loopback_on_an_ephemeral_port',
                 'test_listener_never_binds_a_wildcard_or_reuses_the_api_port',
                 'test_authorization_request_uses_the_exact_loopback_redirect_uri',
                 'test_wrong_callback_path_is_rejected',
                 'test_wrong_method_is_rejected_without_touching_attempt_state',
                 'test_oversized_request_line_is_rejected', 'test_oversized_query_is_rejected',
                 'test_listener_closes_after_a_terminal_callback',
                 'test_listener_closes_after_its_deadline')},
    {'id': 'A7-IDENTITY', 'source': 'ADR-0007 Decision: identity binding; threat delta TM-3 tests', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'The credential binds to the identity Google authenticated, never to intent, and cannot attach to a conflicting account record.',
     'tests': _t(OAUTH, 'test_the_profile_is_queried_as_me_with_a_bearer_token',
                 'test_the_returned_identity_overrides_any_intent_or_login_hint',
                 'test_an_invalid_or_malformed_profile_is_rejected',
                 'test_an_identity_lookup_failure_leaves_no_credential',
                 'test_the_same_identity_cannot_be_connected_to_two_slots',
                 'test_one_credential_key_can_never_be_shared_by_two_connected_records')},
    {'id': 'A7-NEVER-LOGGED', 'source': 'ADR-0007 Decision: never logged; threat delta TM-1 test', 'risks': ['R-16'],
     'abuse_cases': ['TM-1'],
     'requirement': 'Codes and tokens never reach logs, the security-event file, exception strings or the loopback response.',
     'tests': _t(OAUTH, 'test_secret_wrapper_redacts_every_representation',
                 'test_static_response_carries_no_query_data_and_is_not_cacheable',
                 'test_oauth_error_callback_is_handled_without_reflecting_the_message',
                 'test_message_for_never_returns_exception_or_upstream_text')
              + _t(OAUTH_SECRETS, 'test_no_secret_reaches_application_logs',
                   'test_no_secret_reaches_the_security_event_file',
                   'test_no_exception_string_or_traceback_carries_a_secret',
                   'test_a_keyring_failure_message_never_carries_the_token')},
    {'id': 'A7-EXCLUSION', 'source': 'ADR-0007 Decision: backup/export exclusion; threat delta TM-1 test', 'risks': ['R-16'],
     'abuse_cases': ['TM-1'],
     'requirement': 'The credential store is absent from the database, export, backup, diagnostics and every API response.',
     'tests': _t(OAUTH_SECRETS, 'test_no_secret_is_present_in_the_sqlite_database_bytes',
                 'test_no_gmail_column_can_ever_hold_a_secret',
                 'test_the_private_export_contains_no_secret_and_no_credential',
                 'test_a_daily_backup_contains_no_secret',
                 'test_diagnostics_report_only_bounded_connection_state',
                 'test_no_api_response_body_contains_a_secret',
                 'test_the_client_secret_never_reaches_any_persisted_artifact')},
    {'id': 'A7-STORAGE', 'source': 'ADR-0007 Decision: storage; threat delta TM-2', 'risks': ['R-16'],
     'abuse_cases': ['TM-2'],
     'requirement': 'Refresh tokens live only in the native OS store with no plaintext fallback; access tokens and attempts stay in memory.',
     'tests': _t(OAUTH, 'test_a_supported_native_backend_is_accepted',
                 'test_an_unsupported_or_failing_keyring_is_rejected_with_no_plaintext_fallback',
                 'test_a_credential_store_write_failure_leaves_the_account_disconnected',
                 'test_a_database_failure_after_the_credential_write_deletes_that_credential',
                 'test_the_access_token_is_never_persisted_and_is_cleared_after_use',
                 'test_a_connected_account_records_only_non_secret_metadata')
              + _t(OAUTH_SECRETS, 'test_oauth_attempts_are_memory_only_and_never_serialized')},
    {'id': 'A7-ISOLATION', 'source': 'ADR-0007 Decision: per-account isolation', 'risks': ['R-16'],
     'abuse_cases': ['TM-2', 'TM-3'],
     'requirement': 'Each account has its own credential key; one slot cannot affect the other.',
     'tests': _t(OAUTH, 'test_per_account_credential_keys_are_isolated_opaque_and_never_reused',
                 'test_disconnect_leaves_the_other_slot_untouched',
                 'test_a_failure_connecting_one_slot_never_alters_the_other')},
    {'id': 'A7-REVOCATION', 'source': 'ADR-0007 Security impact: revocation', 'risks': ['R-16'],
     'abuse_cases': ['TM-2'],
     'requirement': 'Disconnect removes local access even if Google fails, reports remote revocation truthfully, and sends the token only in the form body.',
     'tests': _t(OAUTH, 'test_disconnect_deletes_the_local_credential_on_successful_revocation',
                 'test_local_disconnection_always_succeeds_and_reports_remote_failure_truthfully',
                 'test_a_malformed_revocation_response_still_removes_local_access',
                 'test_revocation_sends_the_token_in_the_form_body_never_the_query',
                 'test_repeated_disconnect_is_idempotent',
                 'test_disconnect_invalidates_a_pending_attempt',
                 'test_disconnect_removes_the_refresh_token_and_the_client_secret',
                 'test_a_disconnected_identity_is_absent_from_every_sqlite_artifact')},
    {'id': 'A7-SECONDARY-GATE', 'source': 'ADR-0007 Decision: primary first (OD-012)', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'The second account cannot start an attempt or sync until it is explicitly enabled.',
     'tests': _t(OAUTH, 'test_the_secondary_slot_cannot_start_an_attempt')
              + _t(OAUTH_SECRETS, 'test_the_secondary_slot_reports_not_enabled_through_the_api')
              + _t(SYNC, 'test_secondary_disabled_and_no_connection_refused')},
    {'id': 'A7-CLIENT-SECRET', 'source': 'ADR-0007 Evidence: client-secret amendment', 'risks': ['R-16'],
     'abuse_cases': ['TM-1', 'TM-2'],
     'requirement': 'The Desktop client secret is entered only at a hidden console prompt, kept in its own OS-store namespace and sent only to the token endpoint.',
     'tests': _t(OAUTH, 'test_the_client_secret_is_stored_in_its_own_keyring_namespace',
                 'test_the_setup_command_never_accepts_a_secret_as_an_argument',
                 'test_the_setup_command_reads_only_from_a_hidden_console_prompt',
                 'test_the_secret_is_only_ever_sent_to_the_exact_google_token_endpoint',
                 'test_no_schema_column_can_hold_the_client_secret')
              + _t(OAUTH_SECRETS, 'test_the_client_secret_is_never_exposed_through_the_api',
                   'test_no_frontend_file_can_hold_or_request_a_client_secret',
                   'test_the_client_secret_is_absent_from_the_repository_and_git_history')},
    {'id': 'A7-TRANSPORT', 'source': 'ADR-0007 / R-16 evidence: fixed endpoints', 'risks': ['R-16'],
     'abuse_cases': ['TM-3', 'TM-6'],
     'requirement': 'Google endpoints are fixed, TLS-verified and host-pinned; redirects, proxies and retries are refused and responses are bounded.',
     'tests': _t(OAUTH, 'test_authorization_endpoint_is_fixed_and_not_caller_controlled',
                 'test_token_and_revocation_endpoints_are_the_fixed_google_urls',
                 'test_oauth_client_disables_redirects_proxies_and_bounds_every_timeout',
                 'test_oauth_transport_verifies_tls_and_pins_the_allowed_hosts',
                 'test_token_exchange_rejects_a_redirect_instead_of_following_it',
                 'test_token_exchange_bounds_the_response_size',
                 'test_a_decompression_bomb_is_refused_within_the_size_bound',
                 'test_token_exchange_posts_form_fields_and_is_never_retried')},
    {'id': 'A7-API-BOUNDARY', 'source': 'ADR-0002 boundary applied to the new Gmail routes', 'risks': ['R-16'],
     'abuse_cases': ['TM-3'],
     'requirement': 'Gmail routes keep the Origin, CSRF, Host, session, method and demo-mode controls, and a caller cannot choose an endpoint, scope or credential key.',
     'tests': _t(OAUTH_SECRETS, 'test_state_changing_routes_are_never_reachable_by_get',
                 'test_gmail_routes_stay_behind_the_existing_origin_csrf_and_host_controls',
                 'test_gmail_routes_require_a_session_when_an_access_key_is_configured',
                 'test_a_caller_cannot_choose_an_endpoint_scope_or_credential_key',
                 'test_an_invalid_account_slot_is_rejected')
              + _t(ASSURANCE, 'test_every_private_route_is_denied_in_demo_mode_and_without_a_session')},

    # ---- ADR-0008: read-only mailbox trust boundary (R-17) ---------------
    {'id': 'A8-READ-ONLY', 'source': 'ADR-0008 Decision: no mutation', 'risks': ['R-17'],
     'abuse_cases': ['TM-5'],
     'requirement': 'No code path can call a mutating Gmail operation; only bounded list/get reads are sent.',
     'tests': _t(OAUTH, 'test_the_gmail_client_wrapper_exposes_no_mutating_operation')
              + _t(SYNC, 'test_actual_wire_methods_queries_and_size', 'test_client_cannot_enumerate_mailbox',
                   'test_gmail_id_response_must_match_request')
              + _t(SYNC_PRIVACY, 'test_no_message_mutation_or_content_io_capabilities')},
    {'id': 'A8-NON-RETENTION', 'source': 'ADR-0008 Decision: memory-only bodies; Evidence', 'risks': ['R-17'],
     'abuse_cases': ['TM-5'],
     'requirement': 'No full body or HTML reaches the database, its sidecars, any disk cache, export, backup or API.',
     'tests': _t(SYNC_PRIVACY, 'test_nonretention_across_storage_and_public_outputs',
                 'test_no_body_or_auth_columns_and_unique_message_constraint')
              + _t(OAUTH, 'test_no_mailbox_message_or_thread_data_is_persisted')
              + _t(STATE_PRIVACY, 'test_transition_history_has_no_column_for_message_content',
                   'test_hostile_evidence_tokens_never_reach_durable_storage',
                   'test_review_queue_exposes_no_field_beyond_45s_minimized_evidence')},
    {'id': 'A8-DISCONNECT', 'source': 'ADR-0008 Decision: disconnect and retention', 'risks': ['R-17'],
     'abuse_cases': ['TM-1'],
     'requirement': 'Disconnect removes the token and sync state but keeps evidence; erasure is a separate explicit action.',
     'tests': _t(OAUTH, 'test_disconnect_clears_only_that_accounts_sync_state',
                 'test_disconnect_never_touches_application_records')
              + _t(OAUTH_SECRETS, 'test_disconnect_is_not_a_data_erasure')
              + _t(SYNC_PRIVACY, 'test_disconnect_preserves_evidence_but_full_erase_removes_it')
              + _t(STATE_PRIVACY, 'test_disconnect_preserves_evidence_state_and_history',
                   'test_full_erase_removes_state_history_links_and_evidence')},
    {'id': 'A8-BOUNDED-SYNC', 'source': 'ADR-0008 Decision: query-level narrowing', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'Sync uses a bounded, ASTRA-built query window with capped pages and retries and never widens on a bad checkpoint.',
     'tests': _t(SYNC, 'test_pagination_resumes_frozen_window_without_skipping',
                 'test_invalid_page_checkpoint_resets_without_widening',
                 'test_page_count_bound_and_repeated_token', 'test_bounded_retries',
                 'test_deadline_does_not_commit_half_page',
                 'test_failures_do_not_advance_cursor_and_clear_access')},
    {'id': 'A8-MULTI-SIGNAL', 'source': 'ADR-0008 Decision: HIGH needs independent signals; threat delta TM-4 test', 'risks': ['R-17', 'R-18'],
     'abuse_cases': ['TM-4'],
     'requirement': 'A single matched element never reaches HIGH; a spoofed message per supported template never reaches HIGH.',
     'tests': _t(SYNC, 'test_positive_extracts_all_fields', 'test_independent_signals_are_required',
                 'test_one_signal_never_high',
                 'test_multiple_contradictory_body_templates_cannot_be_high',
                 'test_malformed_text_never_establishes_high',
                 'test_later_stage_quoted_confirmations_are_excluded')},
    {'id': 'A8-AUTH-CAP', 'source': 'ADR-0008 Decision: authentication evidence; threat delta TM-4 test', 'risks': ['R-17', 'R-18'],
     'abuse_cases': ['TM-4'],
     'requirement': 'Missing, failed, foreign, misaligned or contradictory authentication evidence caps an otherwise strong match at exactly MEDIUM, so it reaches Needs Review.',
     'tests': _t(SYNC, 'test_independent_signals_are_required')
              + _t(ASSURANCE, 'test_authentication_failure_caps_a_strong_template_at_exactly_medium')
              + _t(STATE, 'test_medium_evidence_enters_needs_review_without_mutation')},
    {'id': 'A8-HOSTILE-CONTENT', 'source': 'ADR-0008 Security impact: malicious content; threat delta TM-5 test', 'risks': ['R-17'],
     'abuse_cases': ['TM-5', 'TM-7'],
     'requirement': 'Email HTML becomes inert text, dangerous URLs are dropped, links are never followed, and the UI has no raw-HTML sink.',
     'tests': _t(SYNC, 'test_html_is_text_and_no_active_links_survive', 'test_dangerous_urls_rejected')
              + _t(SYNC_PRIVACY, 'test_no_message_mutation_or_content_io_capabilities')
              + _t(ASSURANCE, 'test_frontend_has_no_raw_html_sink')},
    {'id': 'A8-PARSER-BOUNDS', 'source': 'Threat delta TM-6 test (email)', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'Oversized, malformed and deeply nested messages are bounded and skipped without unbounded memory or time.',
     'tests': _t(SYNC, 'test_malformed_and_oversized_encoding', 'test_mime_depth_parts_and_byte_budget',
                 'test_oversized_message_skipped_and_outside_window_not_recorded',
                 'test_invalid_list_never_silently_completes')
              + _t(SYNC_PRIVACY, 'test_wire_and_decoded_caps_and_error_privacy',
                   'test_parser_failure_is_counted_without_exception_or_content_leak')},
    {'id': 'A8-MAILBOX-TRANSPORT', 'source': 'Threat delta, issue #45 implementation delta', 'risks': ['R-16', 'R-17'],
     'abuse_cases': ['TM-1', 'TM-6'],
     'requirement': 'Mailbox reads use pinned dialing, verified TLS and bounded deadlines, and private transport traces never leak.',
     'tests': _t(SYNC_PRIVACY, 'test_actual_dial_pinned_deadline_and_tls',
                 'test_mailbox_tls_cannot_write_session_keys_from_environment',
                 'test_transport_debug_headers_suppressed_only_during_request',
                 'test_storage_failures_never_reach_generic_traceback_log',
                 'test_new_routes_inherit_browser_guards', 'test_sync_api_and_account_gate')},

    # ---- ADR-0009: external job-provider trust boundary (R-17) -----------
    {'id': 'A9-SSRF', 'source': 'ADR-0009 Decision: URL validation; Evidence; threat delta TM-7 test', 'risks': ['R-17'],
     'abuse_cases': ['TM-7'],
     'requirement': 'Loopback, private-range, link-local and credentialed URLs are rejected before fetch, at connect time and on every redirect.',
     'tests': _t(CONTROLS, 'test_ssrf_blocks_private_and_dangerous_targets')
              + _t(TRANSPORT, 'test_loopback_destination_rejected_at_connect_time',
                   'test_structural_validation_never_resolves_dns_itself',
                   'test_connect_tcp_dials_the_pinned_resolved_ip_not_the_hostname',
                   'test_any_private_address_in_a_mixed_dns_result_blocks_the_destination',
                   'test_redirect_target_is_revalidated_and_a_blocked_target_is_typed',
                   'test_initial_policy_block_is_typed_not_a_raw_valueerror_escaping',
                   'test_bounded_redirect_cycle_gives_up_with_too_many_redirects')
              + _t(REMEDIATION, 'test_invalid_idna_redirect_is_typed')
              + _t(REMEDIATION_2, 'test_lever_credentialed_url_rejected_not_accepted',
                   'test_ashby_credentialed_url_rejected_not_accepted')
              + _t(PROVIDERS, 'test_non_http_url_is_rejected',
                   'test_invalid_board_rejected_before_any_network_call')},
    {'id': 'A9-RESPONSE-CAPS', 'source': 'ADR-0009 Decision: response limits; threat delta TM-6 test', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'Provider responses are size-capped (encoded and decoded) and deadline-bounded, independent of the parked R-13 branch.',
     'tests': _t(TRANSPORT, 'test_oversized_streamed_response_is_rejected',
                 'test_misleading_content_length_does_not_bypass_the_real_byte_count',
                 'test_one_byte_over_cap_is_rejected',
                 'test_compression_bomb_rejected_without_materializing_the_full_expansion',
                 'test_concatenated_gzip_members_rejected_not_looped_forever',
                 'test_deadline_expiring_mid_stream_aborts_before_returning_success',
                 'test_retry_sequence_cannot_extend_past_the_deadline',
                 'test_huge_retry_after_is_capped_not_honored_verbatim')
              + _t(REMEDIATION, 'test_slow_headers_obey_absolute_deadline_through_httpcore')
              + _t(LEVER, 'test_pagination_bound_caps_pages_and_records')},
    {'id': 'A9-OVERSIZED-ISOLATION', 'source': 'ADR-0009 Evidence: oversized response does not block other providers', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'A provider whose response exceeds the cap fails alone; the other providers in the same scan still import.',
     'tests': _t(ASSURANCE, 'test_an_oversized_provider_response_fails_only_that_source')},
    {'id': 'A9-STRICT-PARSING', 'source': 'ADR-0009 Decision: parsing', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'Unexpected payload shapes fail closed; bad rows are rejected individually; only documented fields are extracted.',
     'tests': _t(PROVIDERS, 'test_unexpected_top_level_shape_fails_closed', 'test_jobs_not_a_list_fails_closed',
                 'test_row_missing_required_field_is_rejected_not_the_whole_board',
                 'test_wrong_field_type_is_rejected_per_row',
                 'test_detail_with_unrelated_keys_is_rejected_not_counted_as_success',
                 'test_dict_content_is_rejected_not_silently_emptied')
              + _t(LEVER, 'test_malformed_first_page_response_is_a_full_failure')
              + _t(ASHBY, 'test_unexpected_top_level_shape_fails_closed', 'test_malformed_url_does_not_raise')
              + _t(TRANSPORT, 'test_invalid_json_body_rejected',
                   'test_unexpected_content_type_rejected_even_if_body_parses')},
    {'id': 'A9-UI-SANITIZATION', 'source': 'ADR-0009 Decision: UI sanitization; Evidence', 'risks': ['R-17'],
     'abuse_cases': ['TM-5'],
     'requirement': 'Provider HTML is reduced to text before storage, and the UI renders provider text only through escaping text sinks.',
     'tests': _t(GREENHOUSE, 'test_escaped_html_content_is_cleaned_to_plain_text')
              + _t(ASSURANCE, 'test_frontend_has_no_raw_html_sink')},
    {'id': 'A9-AI-FRAMING', 'source': 'ADR-0009 Decision: AI-bound framing; Evidence', 'risks': ['R-17'],
     'abuse_cases': ['TM-10'],
     'requirement': 'Provider text reaches a model only as delimited data, with no tools offered, a strict output schema, and no ability to change application state.',
     'tests': _t(CONTROLS, 'test_prompt_injection_stays_data')
              + _t(ASSURANCE, 'test_ai_requests_offer_no_tools_and_frame_provider_text_as_data',
                   'test_hostile_model_output_is_rejected',
                   'test_model_advice_through_the_api_changes_no_application_state')},
    {'id': 'A9-FAILURE-ISOLATION', 'source': 'ADR-0009 Decision: failure isolation', 'risks': ['R-17'],
     'abuse_cases': ['TM-6'],
     'requirement': 'One provider failure never blocks, rolls back or corrupts another provider in the same scan.',
     'tests': _t(ISOLATION, 'test_one_provider_failure_does_not_affect_others_first_permutation',
                 'test_one_provider_failure_does_not_affect_others_second_permutation',
                 'test_no_provider_module_uses_httpx_directly')
              + _t(PROVIDERS, 'test_one_items_detail_failure_does_not_void_the_rest')
              + _t(ASHBY, 'test_board_returning_404_is_isolated_typed_failure_not_a_crash')},
    {'id': 'A9-PROVENANCE', 'source': 'ADR-0009 Decision: provenance', 'risks': ['R-17'],
     'abuse_cases': ['TM-8'],
     'requirement': 'Every normalized record keeps its source adapter and original URL.',
     'tests': _t(REMEDIATION_2, 'test_original_source_url_preserved_exactly_for_navigation',
                 'test_greenhouse_job_url_is_source_url')
              + _t(LEVER, 'test_compatibility_preserves_workplace_type_and_source_label')
              + _t(ASHBY, 'test_compatibility_carries_real_remote_status_and_source_label')},

    # ---- Threat delta: reconciliation and status evidence (R-18) ---------
    {'id': 'TM-RECONCILE', 'source': 'Threat delta TM-8 test', 'risks': ['R-18'],
     'abuse_cases': ['TM-8'],
     'requirement': 'Merging needs multi-field agreement; a single field never merges; a contradictory requisition URL blocks linking; ambiguity never mutates.',
     'tests': _t(STATE, 'test_a_single_matching_field_never_merges_records',
                 'test_two_agreeing_fields_are_still_not_a_strong_match',
                 'test_different_employer_produces_no_candidate_at_all',
                 'test_ambiguous_matches_never_mutate_or_create_an_application',
                 'test_conflicting_requisition_urls_never_auto_link',
                 'test_conflicting_urls_are_a_contradiction_not_a_missing_field',
                 'test_generic_roots_establish_no_identity_and_contradict_nothing',
                 'test_unmatched_evidence_never_fabricates_a_job_or_application',
                 'test_existing_manual_application_is_never_duplicated',
                 'test_malformed_or_unsafe_urls_never_become_identity_evidence',
                 'test_replaying_the_same_evidence_creates_no_second_transition',
                 'test_concurrent_reconciliation_produces_one_link_and_one_transition')
              + _t(DEDUPE, 'test_candidate_only_never_auto_merges',
                   'test_three_record_transitive_bridge_never_collapses',
                   'test_composite_fingerprint_requires_all_three_signals')},
    {'id': 'TM-STATUS-SPOOF', 'source': 'Threat delta TM-9 test', 'risks': ['R-18'],
     'abuse_cases': ['TM-9'],
     'requirement': 'No automated signal can set a later-stage state; only HIGH may apply APPLIED; weaker signals never override a manual state.',
     'tests': _t(STATE, 'test_every_state_pair_matches_the_declared_table',
                 'test_weak_evidence_cannot_set_a_later_state',
                 'test_even_high_confidence_cannot_set_a_later_state',
                 'test_only_high_confidence_may_apply_a_transition',
                 'test_low_evidence_never_transitions_and_never_queues',
                 'test_manual_state_is_never_superseded_by_automated_evidence',
                 'test_medium_evidence_cannot_downgrade_a_manually_confirmed_state',
                 'test_a_manually_created_state_cannot_be_reasserted_by_gmail_evidence',
                 'test_history_is_append_only_and_carries_full_provenance')
              + _t(STATE_PRIVACY, 'test_no_route_sets_a_state_directly')},
    {'id': 'TM-AUDIT-EVENTS', 'source': 'Threat delta: logging/telemetry impact', 'risks': ['R-16', 'R-17', 'R-18'],
     'abuse_cases': ['TM-1', 'TM-8'],
     'requirement': 'OAuth, sync, parser and reconciliation events carry only bounded taxonomy fields.',
     'tests': _t(OAUTH_SECRETS, 'test_security_events_record_only_bounded_taxonomy_fields',
                 'test_arbitrary_event_fields_are_still_discarded')
              + _t(STATE_PRIVACY, 'test_security_events_record_only_bounded_tokens',
                   'test_unknown_security_event_fields_are_dropped',
                   'test_url_conflict_security_event_is_bounded')},
    {'id': 'TM-PRIVACY-PATHS', 'source': 'Threat delta: privacy impact (export/deletion extended)', 'risks': ['R-17', 'R-18'],
     'abuse_cases': ['TM-1'],
     'requirement': 'Export and deletion cover the new evidence and state tables; full erase removes them.',
     'tests': _t(STATE_PRIVACY, 'test_export_includes_the_new_minimized_tables',
                 'test_privacy_counts_cover_the_new_tables',
                 'test_export_and_backup_carry_no_46_sourced_sentinels',
                 'test_history_deletion_removes_state_history_and_links_not_evidence')
              + _t(OAUTH, 'test_full_local_deletion_also_removes_the_client_secret')
              + _t(OAUTH_SECRETS, 'test_full_local_deletion_removes_gmail_credential_access')},
    {'id': 'TM-AI-EMAIL-GUARD', 'source': 'Threat delta TM-10 (not yet applicable)', 'risks': ['R-17'],
     'abuse_cases': ['TM-10'],
     'requirement': 'Current mailbox/state sources declare no known AI imports, including inside functions, and load no AI module at import time. This dependency guard does not prove complete runtime reachability; introducing AI classification still requires a threat-model delta.',
     'tests': _t(ASSURANCE, 'test_mailbox_and_state_sources_have_no_declared_ai_imports_or_import_time_ai_dependencies',
                 'test_ai_dependency_guard_detects_nested_and_literal_dynamic_imports')},
]


def node_ids():
    """Every test function this inventory relies on, as `path::name`."""
    seen = []
    for requirement in REQUIREMENTS:
        for node in requirement['tests']:
            if node not in seen:
                seen.append(node)
    return seen


def selected():
    """(path, function name) pairs for the conftest marker hook."""
    return {tuple(node.split('::', 1)) for node in node_ids()}
