# Framework lessons — what to avoid, what to exceed

Design input for primavera's security and framework model, from a
multi-source, adversarially-verified survey (2026-07-19) of how the
mainstream enterprise frameworks handle authn/authz and pipeline
composition. Every claim below was confirmed by a 3-vote refutation panel
against primary sources (framework advisories, official docs, OWASP); the
citations are the surviving primary sources.

> **Honest scope.** Verification survived in depth for **Spring Security,
> ASP.NET Core, and Django only**. Nothing verifiable landed for Jakarta EE,
> Quarkus, Micronaut, FastAPI, or NestJS, and the compile-time-DI-tradeoffs
> half of the brief (what Quarkus/Micronaut sacrificed) did not survive —
> those remain open questions (§4), not gaps in the frameworks. So the
> synthesis below is grounded in the **security-pipeline** evidence, which
> turned out to converge hard on a single theme.

## The one dominant finding

All three verified frameworks assemble security behavior at **runtime** from
**ordered chains** — Spring's `SecurityFilterChain`, ASP.NET's middleware
registration order in `Program.cs`, Django's `MIDDLEWARE` list — whose
correctness depends on declaration order, string-based path matching, and
inter-component coupling that is **documented but never enforced at compile
time**. The recurring authorization-bypass CVEs arise not from a single
misuse but at the **interaction seams between independently-configured
subsystems**. This is precisely the class an ownership-based,
compile-time-DI framework is positioned to eliminate — and it is primavera's
clearest differentiation opportunity.

## Things to avoid (ranked), each with the principle that avoids it

### 1. Ordering as an unenforced convention
All three stacks make security-pipeline ordering load-bearing yet
un-checked. Spring's docs state authentication filters *must* run before
authorization filters; ASP.NET's docs call `UseCors → UseAuthentication →
UseAuthorization` order "critical for security"; Django requires
`CsrfViewMiddleware` before any login-performing auth middleware (login
rotates the CSRF secret) and `AuthenticationMiddleware` after
`SessionMiddleware`. Every one of these is prose; misordering compiles/starts
clean and fails at request time (Django) or silently (ASP.NET).
[Spring architecture][sa], [ASP.NET middleware][am], [Django middleware][dm]

> **Principle — pipeline order is a typed, compile-time property.** primavera
> expresses the security pipeline as a statically-ordered composition where
> stage dependencies (context-before-both, authn-before-authz,
> csrf-before-login) are encoded so misordering **fails compilation**, not
> production. This is the natural home for the scope/aspect substrate we
> already build on.

### 2. Ambiguous string-based path matching in security rules
Spring's **CVE-2023-34035** (HIGH): `requestMatchers(String)` could not
decide whether a pattern was an MVC pattern or a plain-servlet pattern in
multi-servlet apps, so classpath contents + servlet topology silently
determined which rules applied. `FilterChainProxy` runs only the **first**
matching chain, so declaration order + pattern interpretation decide
coverage. The fix throws — **at runtime**. [CVE-2023-34035][c1]

> **Principle — security rules reference typed route/handler identities, not
> strings.** A rule names the handler it protects; there is no string
> re-interpreted by context. Ambiguous coverage is a compile error, not a
> runtime exception.

### 3. "Authorization rules don't actually cover the request they appear to"
Spring's **CVE-2024-38821** (CRITICAL): WebFlux static-resource
authorization bypassed when three independently-enabled features coincided,
driven by **un-normalized URL variants** slipping past the security matcher
while the resource handler still resolved them. [CVE-2024-38821][c2]

> **Principle — normalize once, before any security decision, and prove
> total coverage.** Path normalization happens in exactly one place, ahead of
> authorization; the framework can show at build time that **every reachable
> handler is covered by some rule** (the decidability of this is open — §4).

### 4. Locale/encoding-dependent comparison in security paths
Spring's **CVE-2024-38827**: authorization bypass from locale-dependent
`String.toLowerCase()/toUpperCase()` (Turkish dotted/dotless I). Long-lived
across two major versions (5.7.x–6.3.x), not a regression. [CVE-2024-38827][c3]

> **Principle — locale-independent, normalized comparison by construction.**
> An opaque normalized-path/identifier type whose only operations are
> locale-independent makes the unsafe comparison *unrepresentable*, not just
> discouraged.

### 5. Default-open islands inside a default-closed system
ASP.NET places Static File Middleware before authentication with "no
authorization checks" — everything under `wwwroot` is public by default.
A documented default-open island in an otherwise default-closed model.
[ASP.NET middleware][am]

> **Principle — default-closed is uniform, no exempt request class.** Static
> assets included; "public" is an explicit, visible opt-out that appears in
> the code, never an implicit exemption.

### 6. Transport hardening as opt-in
Django ships `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_SSL_REDIRECT` = `False` and `SECURE_HSTS_SECONDS` = `0`; hence
`manage.py check --deploy` exists as a bolt-on audit. [Django settings][ds]

> **Principle — invert it: production profiles default secure.** Secure
> cookies, HSTS, HTTPS-redirect **on**; development relaxation is explicit
> and compile-time-visible in the build profile (primavera already has
> profile-selected wiring). The deploy checklist disappears into the profile
> type.

## Things to improve on (get right → exceed)

### A. ASP.NET's policy-based authorization — the model to beat
ASP.NET's role- and claims-based authz are both built on **one** primitive
(requirement + handler + policy), decoupled from routing, invocable
imperatively anywhere. Explicit combinators — requirements AND within a
policy, multiple handlers OR for one requirement, `context.Fail` as veto —
and **default-closed** evaluation (success only via explicit `Succeed`).
One footgun: `InvokeHandlersAfterFailure` defaults to `true`. [ASP.NET policies][ap]

> **Better-than-parity.** Adopt a single default-closed policy algebra as the
> *only* authz primitive; make AND/OR/veto **first-class typed expressions
> checked at compile time**; make post-denial handler execution **opt-in per
> handler** (for audit) rather than a global default.

### B. Django's CSRF — the reference design to adopt nearly wholesale
Secret **rotates on every login** (built-in fixation defense); token
**masked with a fresh per-response random mask** to defeat BREACH, comparing
only the unmasked secret; **Origin checked** against host + trusted origins
for HTTPS, strict-Referer fallback when Origin absent. [Django CSRF][dc]

> **Better-than-parity.** Keep rotation/masking/Origin semantics; solve the
> documented stale-token DX cost (pre-login forms in other tabs break) with
> grace-window dual-secret validation; make the HTTP-no-Referer gap moot by
> refusing non-HTTPS in production profiles (per avoid-#6).

### C. Django's secure-by-default core — replicate, then type the escape hatches
Auto-escaping on by default (docs honestly admit it is "not entirely
foolproof"); ORM parameterized by construction; `mark_safe` / `raw()` /
`extra()` are the documented weakening points. One verified qualification:
parameterization protects **values, not identifiers/aliases** (patched
alias-position CVEs exist). [Django security][dsec]

> **Better-than-parity.** Default-on protection everywhere, but make the
> escape hatches **typed and auditable** — an unsafe-HTML type and an
> unsafe-SQL *capability* that appear in signatures — and close the
> identifier-position parameterization gap Django's design leaves open.

## Cross-references

Feeds primavera-spec **§8 (Security)** — the protocol matrix — and the
future `docs/Security.md`. Avoid-#1/#2/#3 are the compile-time-coverage
argument for typed routes at the Phase-4 web boundary; avoid-#6 binds to the
deployment-profile design (§3.6); improve-A is the authz-algebra decision
behind `@RolesAllowed`/`@Secured`; improve-B/C set the CSRF and
escape-hatch-typing defaults.

## Open questions (unverified — do not treat as settled)

1. What did Quarkus/Micronaut concretely sacrifice by moving DI to compile
   time (dynamic bean replacement, conditional config, ecosystem compat), and
   which costs bite primavera? No claim survived verification.
2. Do the unexamined stacks (Jakarta EE, Quarkus, Micronaut, FastAPI,
   NestJS) confirm the ordering/path-matching-as-convention pattern?
3. Current first-class passkey/WebAuthn and OAuth 2.1/OIDC maturity across
   these frameworks, and what compile-time-verified protocol integration
   looks like. (Unverified signal from fetch stage: both Spring Security and
   ASP.NET Core Identity now ship first-party WebAuthn — corroborates §8's
   Tier-2 passkey placement, but did not pass the verification gate.)
4. Can "every reachable handler is covered by an authorization rule" be made
   a **decidable compile-time property** with typed routes, and how have
   partial attempts (Spring's runtime ambiguity exception, ASP.NET's ASP0001
   analyzer, fallback-policy patterns) fallen short?

[sa]: https://docs.spring.io/spring-security/reference/servlet/architecture.html
[am]: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/middleware/?view=aspnetcore-10.0
[dm]: https://docs.djangoproject.com/en/6.0/ref/middleware/
[c1]: https://spring.io/security/cve-2023-34035/
[c2]: https://spring.io/security/cve-2024-38821/
[c3]: https://spring.io/security/cve-2024-38827/
[ds]: https://docs.djangoproject.com/en/6.0/ref/settings/
[ap]: https://learn.microsoft.com/en-us/aspnet/core/security/authorization/policies?view=aspnetcore-10.0
[dc]: https://docs.djangoproject.com/en/6.0/ref/csrf/
[dsec]: https://docs.djangoproject.com/en/6.0/topics/security/
