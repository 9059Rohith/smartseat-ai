# Managed authentication acceptance

Evidence recorded 2026-11-05 against `https://smartseat-ai-9059.vercel.app` and the dedicated Supabase project `tnwrnwhitnbxuhdfuwvh`.

## Verified

- The live provider exposes email and Google authentication, allows signup and requires email confirmation (`mailer_autoconfirm: false`). Confirmation was never disabled.
- The authenticated Supabase CLI 3.0.0 configuration diff has no declared Auth configuration drift. Production callback, recovery callback and confirmation redirects match the checked-in application configuration. The minimum password length is 12 and anonymous signup is disabled.
- Seven safe live checks pass: public provider configuration, signed-out `/api/me`, anonymous account denial, anonymous restaurant-state denial, expired-session denial with rejected refresh and cookie clearing, missing confirmation-token rejection, and invalid signup validation before any account/email side effect.
- The application validates identity with the managed Auth provider. A locally unexpired forged session cannot access account data. Anonymous managed identities cannot access owner accounts.
- With a controlled Auth HTTP boundary, an expired access token can refresh successfully and return a validated identity. Refreshed session cookies retain `Secure`, `HttpOnly` and `SameSite=Lax`. A rejected refresh removes the invalid session cookie and private state returns HTTP 401. Private API responses use `Cache-Control: no-store`.
- Controlled provider checks cover unconfirmed-email sign-in rejection, expired recovery confirmation rejection, restricted-email signup failure, password-update denial without a valid session and recovery rate limits. They use the real application handlers and Supabase SDK; only external provider HTTP responses are simulated.
- Fixed a false-success path: recovery provider failures other than HTTP 429 now return a generic HTTP 503 service-unavailable response. Provider details and account existence are not disclosed. The regression test failed with HTTP 200 before the fix and passes after it.
- A successful recovery request generates a PKCE challenge and stores its verifier in a secure server cookie, with the exact production recovery callback. Controlled success responses keep the account-existence wording conditional.

## Owner recovery email delivery verified; full lifecycle remains unaccepted

Two recovery transactions were requested for the existing owner's address on 2026-11-05, within the default two-per-hour allowance. The first direct provider request returned HTTP 200 with an empty response. The root agent then verified the owner's existing Gmail browser session and observed the actual Supabase **Reset Your Password** email at **5:17 PM IST**, containing the correct dedicated-project recovery callback.

After signing out of SmartSeat, the root agent used the deployed app's **Forgot Password** form to submit one second recovery request at **5:32 PM IST**. The provider accepted it and a fresh email arrived in that same verified owner Gmail session, again containing the correct project callback. The root agent opened that latest message and followed its actual **Reset Password** button. The recovery link completed the application's PKCE exchange and a new browser tab landed at `https://smartseat-ai-9059.vercel.app/?reset_password=1`, displaying **Choose a new password**, a password field requiring at least 12 characters, and an **Update password** button. This verifies owner-mailbox delivery, the browser-originated request, recovery callback exchange and reset-form entry end to end. The agent stopped before typing or submitting any new password; the owner's actual password remains unchanged. Recovery tokens and link secrets are omitted from this record.

The Gmail connector is linked to a different account, so its earlier narrow zero-result lookup was not delivery evidence. The later browser observations above establish owner-mailbox delivery. No OAuth scopes were expanded, unrelated mail or credentials retrieved, further recovery messages sent, or existing password changed.

No configured custom SMTP section was reported by the dedicated project's CLI Auth config diff/pull. A key-name-only check of known existing project environment files found no SMTP, Resend, SendGrid, Brevo, Postmark or mail credentials. No credentials were copied or paid service enabled. Supabase's default mail service restricts recipients to organization-team addresses, currently limits delivery to two messages per hour and has no production delivery guarantee. Public email signup and recovery cannot be advertised as production accepted until authorized SMTP delivery and the real links are verified. Google sign-in acceptance is tracked separately.

Public signup email verification, public recovery delivery outside the organization-team restriction, completion of the password update and a complete real email/password login/logout/password-reset sequence remain unaccepted. Owner recovery delivery and reset-form entry do not establish those flows. No account was auto-confirmed and no owner password was changed to manufacture that result.

## Reproduce

```powershell
node --test tests/cloud/*.test.cjs
node tests/cloud/auth-acceptance-live.cjs
```

The final cloud Node suite passes 22 tests, including 12 authentication acceptance cases and the independent router identity regression. The live script makes seven read/validation requests and creates no users, emails, workspaces or restaurant records. `SMARTSEAT_ACCEPTANCE_ORIGIN` optionally targets a different deployment. The password-recovery 503 fix is included in the production deployment verified on this release pass; its provider-failure regression is checked locally without consuming the live email allowance.

These tests establish invalid/expired-session handling and secure refresh behavior. They do not establish a paid provider inactivity-timeout feature or a real wall-clock expiry of the owner's browser session. Supabase's free plan normally keeps sessions active through token refresh; managed time-boxed and inactivity session controls are paid-plan features and were not enabled.

Sources: [Supabase SMTP limitations](https://supabase.com/docs/guides/auth/auth-smtp), [Supabase session lifetime and refresh](https://supabase.com/docs/guides/auth/sessions), [Supabase CLI v3 changes](https://supabase.com/changelog/supabase-cli-v3).
