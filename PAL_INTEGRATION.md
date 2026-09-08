# PAL AI Jobs Integration

## Launch
1. Authenticated participant selects `START EXPERIENCE`.
2. Backend creates a one-time launch nonce and a short-lived signed token containing only subject UUID, opaque event identifier, issued/expiry times, audience and nonce.
3. Browser is redirected to the configured PAL HTTPS endpoint with the token. No name, email, staff ID or sensitive profile data appears in the URL.
4. PAL validates signature, expiry, issuer, audience and nonce before creating/continuing its local session.

Use asymmetric signing (ES256/RS256) in production so PAL receives only the public verification key. Local development may use Django signing behind an adapter.

## Callback
PAL POSTs JSON to the callback endpoint with external result ID, participant subject, nonce, completion status and only approved result fields. The request includes timestamp, key ID and signature over the raw body.

The receiver verifies signature, clock skew, nonce, participant and payload schema; rejects replayed external result IDs; stores the minimal result; records payload checksum; and creates the idempotent PAL Learning XP transaction/badge on completion.

## Stored fields
Completion status, career/role label, optional AI risk score, Career HP, skill-gap summary, recommendation summary and optional HTTPS risk-card URL. Raw sensitive assessment answers are not required by Learning Week and are not stored.

## Failure handling
Callback responses are idempotent. PAL retries 5xx/timeouts. Admin can inspect integration status and replay metadata, but secrets/tokens are redacted. Participant sees a resumable pending state rather than a false completion.
