"""Configure the Gmail OAuth client secret: `python -m backend.gmail_setup`.

Issue #44. Google's installed-app documentation marks `client_secret`
optional and states that installed apps cannot keep a secret confidential,
but a Desktop OAuth client can still enforce client authentication at the
token endpoint -- live validation proved this one does. This command is the
only way a secret enters ASTRA.

Why a console command and not a settings field in the web UI: a browser
form would place the secret in page state, in the DOM, and in a request
body that passes through the local HTTP stack. A hidden console prompt
keeps it in one process's memory until it reaches the OS credential store.

The value is read with `getpass`, which reads the console directly rather
than stdin, so it is not echoed, cannot be piped in from a file or another
process, and does not land in shell history. It is never accepted as a
command-line argument, never written to a file, and never printed.
"""
import getpass
import sys


#: Every line this command can print, authored here. `_report` accepts only
#: a key from this table plus optional bounded tokens, so nothing derived
#: from the entered secret -- not even by way of an exception raised by a
#: function that handled it -- can reach stdout. CodeQL's
#: `py/clear-text-logging-sensitive-data` rule flagged the earlier
#: free-string version on exactly that basis, and it was right to: nothing
#: structurally prevented a future edit from printing the value.
LINES = {
    'banner': 'ASTRA Gmail OAuth client secret setup.',
    'store': 'Credential store : {}',
    'client_id': 'Client ID        : {} (from {})',
    'secret': 'Client secret    : {}',
    'secret_removed': 'Client secret    : {} (removed)',
    'no_store': ('A supported native OS credential store is unavailable. ASTRA '
                 'never falls back to storing a secret in plaintext.'),
    'usage': 'Usage: python -m backend.gmail_setup [--status | --remove]',
    'never_argument': ('The client secret is never accepted as a command-line '
                       'argument.'),
    'prompt_intro': '',
    'no_console': ('No interactive console available for a hidden prompt. Run '
                   'this command from a real terminal window.'),
    'cancelled': 'Cancelled. Nothing was stored.',
    'not_stored': 'Not stored: {}',
    'saved': ('Stored in the OS credential store. Connect Gmail from '
              'Privacy & Local Data.'),
}

#: Tokens `_report` may interpolate. Bounded state words and bounded error
#: codes only -- never free text, never a credential value.
_SAFE_TOKENS = frozenset({
    'OS_SECURE_STORE', 'UNAVAILABLE', 'CONFIGURED', 'NOT_CONFIGURED', 'INVALID',
    'OK', 'CLIENT_SECRET_INVALID', 'CREDENTIAL_STORE_FAILED',
    'CREDENTIAL_STORE_UNAVAILABLE', 'ASTRA_GMAIL_CLIENT_ID',
})


def _report(key, *tokens):
    """Print one authored line, interpolating only allowlisted tokens.

    A token outside `_SAFE_TOKENS` is replaced rather than printed, so an
    unexpected value can never be echoed.
    """
    safe = [token if token in _SAFE_TOKENS else 'UNKNOWN' for token in tokens]
    print(LINES[key].format(*safe), flush=True)


def _paragraph(*lines):
    """Print fixed explanatory text. Literals only, never a parameter."""
    for line in lines:
        print(line, flush=True)


def _report_authored(key, code, message_for):
    """Print a line whose insert is an authored message from the code table.

    `code` is always a literal at its raise site and `message_for` only
    ever returns a module-level constant, so no value entered at the
    prompt can reach this.
    """
    print(LINES[key].format(message_for(code)), flush=True)


def main(argv=None):
    from .gmail_accounts import (client_secret_status, credential_store_status,
                                 delete_client_secret, store_client_secret)
    from .gmail_oauth import (CLIENT_ID_ENVIRONMENT_VARIABLE, OAuthError, Secret,
                              configuration_status, message_for)

    argv = sys.argv[1:] if argv is None else list(argv)
    # A secret passed as an argument would be visible to every process on
    # the machine and would land in shell history, so it is never accepted.
    if any(argument.startswith('--secret') for argument in argv):
        _report('never_argument')
        return 2
    if any(argument not in ('--status', '--remove') for argument in argv):
        _report('usage')
        return 2

    store = credential_store_status()
    _report('store', store['state'])
    if store['state'] != 'OS_SECURE_STORE':
        _report('no_store')
        return 1
    _report('client_id', configuration_status()['state'],
            CLIENT_ID_ENVIRONMENT_VARIABLE)
    _report('secret', client_secret_status()['state'])

    if '--status' in argv:
        return 0

    if '--remove' in argv:
        delete_client_secret()
        _report('secret_removed', client_secret_status()['state'])
        return 0

    _paragraph(
        '',
        'Paste the client secret for your own Desktop OAuth client.',
        'It is not echoed, not written to any file, and never appears in',
        'the database, logs, exports, backups, diagnostics or the UI.',
        'It is stored only in your OS credential store, protected for',
        'your Windows user account. Press Enter with nothing to cancel.')
    # Wrapped immediately, so the value never exists as a bare local string
    # that some later line could interpolate.
    try:
        secret = Secret(getpass.getpass('Client secret (hidden): '))
    except Exception:
        # The exception type is not printed either: it is derived from the
        # call that read the secret.
        _report('no_console')
        return 1
    try:
        if not secret.reveal().strip():
            _report('cancelled')
            return 1
        try:
            store_client_secret(secret)
        except OAuthError as error:
            # Only the bounded code, resolved through the authored message
            # table -- never `str(error)`, which is derived from a function
            # that handled the secret.
            _report_authored('not_stored', error.code, message_for)
            return 1
    finally:
        secret.clear()
    _paragraph('')
    _report('secret', client_secret_status()['state'])
    _report('saved')
    return 0


if __name__ == '__main__':
    sys.exit(main())
