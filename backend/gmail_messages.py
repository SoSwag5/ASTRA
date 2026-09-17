"""GET-only Gmail messages.list/messages.get wrapper (#45 / ADR-0008).

URLs, query predicate, response caps, deadlines and retries are bounded here.
The #44 transport handles credentials, verified TLS, fixed hosts, pinned public
DNS, redirects/proxies and deadline-aware I/O. No mutating Gmail API exists."""
import re
import time
from urllib.parse import quote, urlencode

from . import gmail_oauth as oauth
from .gmail_oauth import OAuthError

#: The Gmail REST root ASTRA uses. `users/me` is resolved by Google from
#: the bearer token, so ASTRA never names a mailbox in a URL -- a bug
#: cannot point this at another account.
_USERS_ME = 'https://gmail.googleapis.com/gmail/v1/users/me/'
#: The message collection (list) and one message (get). These two are the
#: complete Gmail message surface of the entire application.
MESSAGE_LIST_ENDPOINT = _USERS_ME + 'messages'
MESSAGE_GET_ENDPOINT_TEMPLATE = _USERS_ME + 'messages/{message_id}'

#: Every Gmail API URL this module may produce, as compiled patterns. The
#: finished URL is matched against these immediately before the request,
#: so a construction bug cannot reach an unlisted path.
ALLOWED_MESSAGE_URLS = (
    re.compile(r'^https://gmail\.googleapis\.com/gmail/v1/users/me/messages'
               r'(?:\?[A-Za-z0-9_\-.~%=&+]*)?$'),
    re.compile(r'^https://gmail\.googleapis\.com/gmail/v1/users/me/messages/'
               r'[A-Za-z0-9_-]{1,128}(?:\?[A-Za-z0-9_\-.~%=&+]*)?$'),
)

#: Allowlisted query-parameter names. `includeSpamTrash` is deliberately
#: absent: Gmail defaults it to false, so spam and trash are never listed,
#: and omitting the parameter entirely means no code path can turn it on.
LIST_PARAMETERS = frozenset({'q', 'maxResults', 'pageToken'})
GET_PARAMETERS = frozenset({'format'})

#: Gmail message and page-token ids as they may appear in a URL. Anything
#: outside this character set is refused rather than escaped, so a crafted
#: id can never introduce a path segment, a query or a traversal.
MESSAGE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
PAGE_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_\-=]{1,512}$')

# ---------------------------------------------------------------------------
# Resource limits. Every one of these bounds work an email sender or a
# mailbox size could otherwise dictate. They are module constants, never
# configuration and never derived from a Google response.
# ---------------------------------------------------------------------------
#: Wire bytes accepted for one `messages.get`. Larger than #44's shared
#: 256 KiB credential-response cap because a real confirmation email with
#: an HTML part is bigger than a token response, and far smaller than a
#: mailbox message with attachments -- an oversized message is skipped,
#: not streamed.
MAX_MESSAGE_RESPONSE_BYTES = 1_048_576
#: Wire bytes accepted for one `messages.list` page.
MAX_LIST_RESPONSE_BYTES = 262_144
#: Messages requested per page, and pages fetched per sync. Their product
#: bounds one run's listing work regardless of how large the mailbox is.
MAX_PAGE_SIZE = 25
MAX_PAGES = 5
#: Hard ceiling on messages fetched in one sync, applied on top of the
#: page bounds so the two cannot multiply.
MAX_MESSAGES_PER_SYNC = 100
MAX_WINDOW_SECONDS = 90 * 86400
CONFIRMATION_FILTER = ('-in:chats {subject:"thank you for applying" '
    'subject:"thanks for applying" subject:"thank you for your application" '
    'subject:"application received" subject:"application submitted" '
    'subject:"application confirmation" subject:"we received your application" '
    'subject:"your application was sent" '
    '(subject:"your application" {from:greenhouse.io from:greenhouse-mail.io '
    'from:lever.co from:myworkday.com from:myworkdayjobs.com from:workday.com})}')


def build_query(after, before):
    """Only a closed time interval and the authored confirmation predicate."""
    if (type(after) is not int or type(before) is not int
            or not 0 < before - after <= MAX_WINDOW_SECONDS
            or after < int(time.time()) - MAX_WINDOW_SECONDS - 60
            or before > int(time.time()) + 60):
        raise GmailReadError('GMAIL_DESTINATION_NOT_ALLOWED', message_for('GMAIL_DESTINATION_NOT_ALLOWED'))
    return f'after:{after} before:{before} {CONFIRMATION_FILTER}'

LIST_TOTAL_TIMEOUT = 20.0
GET_TOTAL_TIMEOUT = 20.0

#: Bounded, safe retry. Only a transient class of failure is retried, only
#: this many times, with a fixed backoff -- never an exponential loop and
#: never a retry of something Gmail already answered definitively.
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class GmailReadError(OAuthError):
    """A bounded, typed Gmail read failure.

    Subclasses `OAuthError` so it inherits #44's contract: the code is a
    stable token from a fixed set and the message is ASTRA's own authored
    text. No Google body, header, URL or exception string is ever carried
    in it, so a failure cannot become a leak of message or credential
    content.
    """


#: Bounded failure codes this module may raise. Keeping the set closed and
#: named here is what lets the API layer and the security-event taxonomy
#: enumerate them without ever admitting free text.
READ_ERROR_CODES = frozenset({
    'GMAIL_READ_FAILED', 'GMAIL_READ_UNAUTHORIZED', 'GMAIL_READ_FORBIDDEN',
    'GMAIL_READ_RATE_LIMITED', 'GMAIL_READ_NOT_FOUND',
    'GMAIL_RESPONSE_INVALID', 'GMAIL_MESSAGE_TOO_LARGE',
    'GMAIL_DESTINATION_NOT_ALLOWED',
    'GMAIL_SYNC_FAILED',
})

_STATUS_CODES = {
    400: 'GMAIL_RESPONSE_INVALID',
    401: 'GMAIL_READ_UNAUTHORIZED',
    403: 'GMAIL_READ_FORBIDDEN',
    404: 'GMAIL_READ_NOT_FOUND',
    429: 'GMAIL_READ_RATE_LIMITED',
}

_MESSAGES = {
    'GMAIL_SYNC_FAILED': 'Gmail synchronization could not finish. Check local storage availability and retry.',
    'GMAIL_READ_FAILED': 'Gmail could not be read. Nothing was changed.',
    'GMAIL_READ_UNAUTHORIZED': 'Gmail rejected the stored authorization. '
                               'Reconnect the account in Privacy & Local Data.',
    'GMAIL_READ_FORBIDDEN': 'Gmail refused the read request. Nothing was changed.',
    'GMAIL_READ_RATE_LIMITED': 'Gmail is rate limiting requests. Try the sync again later.',
    'GMAIL_READ_NOT_FOUND': 'That Gmail message is no longer available.',
    'GMAIL_RESPONSE_INVALID': 'Gmail returned an unexpected response. Nothing was changed.',
    'GMAIL_MESSAGE_TOO_LARGE': 'A Gmail message exceeded the size ASTRA will read.',
    'GMAIL_DESTINATION_NOT_ALLOWED': 'Gmail requests only ever contact Google over HTTPS.',
}


def message_for(code):
    """Authored text for a bounded read-failure code."""
    return _MESSAGES.get(code, _MESSAGES['GMAIL_READ_FAILED'])


def _checked_url(url):
    """Refuse any URL this module did not intend to build."""
    for pattern in ALLOWED_MESSAGE_URLS:
        if pattern.match(url):
            return url
    raise GmailReadError('GMAIL_DESTINATION_NOT_ALLOWED',
                         message_for('GMAIL_DESTINATION_NOT_ALLOWED'))


def _build(base, parameters, allowed):
    """Compose a URL from fixed parts and allowlisted parameter names."""
    unknown = set(parameters) - allowed
    if unknown:
        # A programming error, not a request. Named by parameter only --
        # values are never echoed.
        raise GmailReadError('GMAIL_DESTINATION_NOT_ALLOWED',
                             message_for('GMAIL_DESTINATION_NOT_ALLOWED'))
    query = urlencode({name: value for name, value in sorted(parameters.items())
                       if value is not None})
    return _checked_url(base + ('?' + query if query else ''))


def _read_only_get(url, *, total_timeout, max_bytes, oversize_code, access_token):
    """GET one allowlisted URL, sharing one deadline across at most three attempts."""
    url = _checked_url(url)
    attempt = 0
    deadline = time.monotonic() + total_timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GmailReadError('GMAIL_READ_FAILED', message_for('GMAIL_READ_FAILED'))
        try:
            status, content_type, body = oauth._request(
                'GET', url, failure_code='GMAIL_READ_FAILED',
                total_timeout=remaining, bearer=access_token,
                max_bytes=max_bytes, oversize_code=oversize_code)
        except OAuthError as error:
            # `oversize_code` is raised only by the response-size bound, so
            # "too large" stays distinguishable from "the request failed"
            # structurally, not by matching message text.
            code = error.code if error.code in READ_ERROR_CODES else 'GMAIL_READ_FAILED'
            raise GmailReadError(code, message_for(code)) from None
        if status in _RETRYABLE_STATUS and attempt < MAX_RETRIES:
            attempt += 1
            time.sleep(min(RETRY_BACKOFF_SECONDS, max(0.0, deadline - time.monotonic())))
            continue
        break
    if status != 200:
        code = _STATUS_CODES.get(status, 'GMAIL_READ_FAILED')
        raise GmailReadError(code, message_for(code))
    if 'application/json' not in content_type.lower():
        raise GmailReadError('GMAIL_RESPONSE_INVALID',
                             message_for('GMAIL_RESPONSE_INVALID'))
    try:
        parsed = oauth._strict_json_object(body, 'GMAIL_RESPONSE_INVALID')
    except OAuthError:
        raise GmailReadError('GMAIL_RESPONSE_INVALID',
                             message_for('GMAIL_RESPONSE_INVALID')) from None
    return parsed


def list_message_ids(access_token, *, query, page_token=None, page_size=MAX_PAGE_SIZE, timeout=LIST_TOTAL_TIMEOUT):
    """Read one bounded page; reject malformed/truncated pagination, never silently finish."""
    match = re.fullmatch(r'after:(\d{1,12}) before:(\d{1,12}) (.*)', query) if isinstance(query, str) else None
    if not match or query != build_query(int(match[1]), int(match[2])):
        # An empty query would list the whole mailbox. Refusing it here
        # means no caller can accidentally widen the sync to everything.
        raise GmailReadError('GMAIL_DESTINATION_NOT_ALLOWED',
                             message_for('GMAIL_DESTINATION_NOT_ALLOWED'))
    if page_token is not None and (not isinstance(page_token, str) or not PAGE_TOKEN_PATTERN.fullmatch(page_token)):
        raise GmailReadError('GMAIL_RESPONSE_INVALID',
                             message_for('GMAIL_RESPONSE_INVALID'))
    size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    url = _build(MESSAGE_LIST_ENDPOINT,
                 {'q': query, 'maxResults': str(size), 'pageToken': page_token},
                 LIST_PARAMETERS)
    parsed = _read_only_get(url, total_timeout=min(LIST_TOTAL_TIMEOUT, timeout),
                            max_bytes=MAX_LIST_RESPONSE_BYTES,
                            oversize_code='GMAIL_RESPONSE_INVALID',
                            access_token=access_token)
    raw = parsed.get('messages', [])
    if not isinstance(raw, list) or len(raw) > size:
        raise GmailReadError('GMAIL_RESPONSE_INVALID', message_for('GMAIL_RESPONSE_INVALID'))
    ids = []
    if isinstance(raw, list):
        for entry in raw[:size]:
            if not isinstance(entry, dict):
                raise GmailReadError('GMAIL_RESPONSE_INVALID', message_for('GMAIL_RESPONSE_INVALID'))
            identifier = entry.get('id')
            if isinstance(identifier, str) and MESSAGE_ID_PATTERN.fullmatch(identifier):
                ids.append(identifier)
            else:
                raise GmailReadError('GMAIL_RESPONSE_INVALID', message_for('GMAIL_RESPONSE_INVALID'))
    token = parsed.get('nextPageToken')
    if token is not None and (not isinstance(token, str) or not PAGE_TOKEN_PATTERN.fullmatch(token)):
        raise GmailReadError('GMAIL_RESPONSE_INVALID', message_for('GMAIL_RESPONSE_INVALID'))
    return ids, token


def fetch_message(access_token, message_id, *, timeout=GET_TOTAL_TIMEOUT):
    """One message in Gmail's `full` format, within a fixed byte cap.

    `full` is required because ADR-0008's parsing works on body
    structure, which `metadata` cannot provide. The raw response is
    returned to the caller as a plain dict and is **never** persisted:
    `backend/gmail_sync.py` extracts the minimized fields from it and
    lets it go out of scope.

    An oversized message raises `GMAIL_MESSAGE_TOO_LARGE` rather than
    being streamed or truncated mid-parse, so a sender cannot make ASTRA
    do unbounded work by attaching a large file.
    """
    if not isinstance(message_id, str) or not MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise GmailReadError('GMAIL_RESPONSE_INVALID',
                             message_for('GMAIL_RESPONSE_INVALID'))
    url = _build(MESSAGE_GET_ENDPOINT_TEMPLATE.format(message_id=quote(message_id, safe='')),
                 {'format': 'full'}, GET_PARAMETERS)
    result = _read_only_get(url, total_timeout=min(GET_TOTAL_TIMEOUT, timeout),
                          max_bytes=MAX_MESSAGE_RESPONSE_BYTES,
                          oversize_code='GMAIL_MESSAGE_TOO_LARGE',
                          access_token=access_token)
    if result.get('id') != message_id or not isinstance(result.get('payload'), dict):
        raise GmailReadError('GMAIL_RESPONSE_INVALID', message_for('GMAIL_RESPONSE_INVALID'))
    return result
