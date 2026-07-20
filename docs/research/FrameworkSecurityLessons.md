# Framework security lessons — what Spring, ASP.NET Core, and Django get wrong (and right)

> Deep-research report, 2026-07-19. Produced by a fan-out research harness:
> 5 search angles → 24 sources fetched (primary-source preference: vendor
> CVE advisories, official framework docs, OWASP) → 120 claims extracted →
> top 25 adversarially verified by 3-vote refutation panels. **All 25
> survived** (23 unanimous, 2 at 2-1 with the dissent incorporated as a
> qualification). Synthesized to 10 findings. Coverage caveats at the end
> matter: this round is deep on **Spring Security, ASP.NET Core, Django**;
> Jakarta EE / Quarkus / Micronaut / FastAPI / NestJS and the general
> DI/config/migration topics did not survive verification and need a
> follow-up round.

## The headline convergence

**One dominant failure class.** In all three stacks, security behavior is
assembled at runtime from *ordered chains* — Spring `SecurityFilterChain`s,
ASP.NET middleware registration order in `Program.cs`, Django's
`MIDDLEWARE` list — whose correctness depends on string-based path
matching, declaration order, and inter-component coupling that is
**documented but never enforced**. The recurring authorization-bypass CVEs
arise at the *interaction seams* between independently-configured
subsystems, not from any single obvious misuse.

**One dominant success pattern.** ASP.NET Core's unified, default-closed
policy algebra for authorization, and Django's secure-by-default core
protections with honestly-documented escape hatches.

## Things to AVOID (ranked), each with the principle that avoids it

1. **Runtime-assembled security pipelines whose ordering is documentation.**
   Spring's docs state filter order is load-bearing ("the Filter that
   performs authentication should be invoked before the Filter that
   performs authorization"); ASP.NET's docs call middleware order "critical
   for security" and mandate `UseCors → UseAuthentication →
   UseAuthorization` "in the order shown"; Django prescribes
   `CsrfViewMiddleware` before any login-performing middleware (login
   rotates the CSRF token) and `AuthenticationMiddleware` after
   `SessionMiddleware` — and **none of the three enforces any of it** at
   build or startup (Django surfaces misordering only as a request-time
   `ImproperlyConfigured`; ASP.NET's sole analyzer covers one narrow case).
   → **Principle: pipeline stages are a typed, statically-ordered
   composition; stage dependencies (context-before-authn,
   authn-before-authz, csrf-before-login) are encoded so misordering fails
   compilation.** This is primavera's clearest differentiation opportunity —
   the strongest cross-framework signal in the dataset.
   [Spring architecture docs; MS middleware docs 2026-06; Django middleware
   ref; spring-security#17664]

2. **String-based, context-ambiguous path matching in security rules.**
   CVE-2023-34035 (HIGH): `requestMatchers(String)` couldn't decide whether
   a pattern was an MVC pattern or a servlet pattern in multi-servlet apps
   — rule misconfiguration emerged from *classpath contents + servlet
   topology + a convenience API*, no single misuse. Spring's fix throws at
   **runtime** in ambiguous cases. First-match-wins chain selection
   compounds it: declaration order silently decides which rules apply.
   → **Principle: security rules reference the typed route/handler they
   protect — never strings reinterpreted by context; coverage/ordering
   ambiguity is a compile error.**
   [spring.io/security/cve-2023-34035; GHSA-4vpr-xfrp-cj64]

3. **Path normalization scattered across subsystems.** CVE-2024-38821
   (Critical): WebFlux static-resource authorization bypassed when three
   independently-enabled features coincided — un-normalized URL variants
   (e.g. trailing backslash) slipped past the security matcher while the
   resource handler still resolved them.
   → **Principle: normalize once, before any security decision; prove at
   build time that every reachable handler is covered by some rule.**
   [spring.io/security/cve-2024-38821]

4. **Locale-dependent operations in security comparisons.**
   CVE-2024-38827: `String.toLowerCase()`'s Turkish-I behavior broke
   case-normalized authorization comparisons — latent across *every
   supported release line* (5.7.x–6.3.x), two major versions.
   → **Principle: security-relevant matching uses locale-independent,
   explicitly-specified folding by construction — ideally an opaque
   normalized-identifier type that makes the locale-sensitive ops
   unrepresentable.** (Cajeta note: `String.operator==` is byte equality —
   already the right default; keep case-folding OUT of security paths.)
   [spring.io/security/cve-2024-38827]

5. **Default-open islands inside default-closed systems.** ASP.NET serves
   everything under `wwwroot` before authentication with "no authorization
   checks" — a documented public-by-default request class in an otherwise
   default-closed model (and exactly where Spring's CVE-2024-38821 lived:
   static resources).
   → **Principle: default-closed is uniform — static assets included;
   public assets are an explicit, visible opt-out.**
   [MS middleware docs 2026-06]

6. **Opt-in transport hardening.** Django ships
   `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`,
   `SECURE_SSL_REDIRECT=False`, `SECURE_HSTS_SECONDS=0`, delegating the
   hardening checklist to operators (`manage.py check --deploy` exists as a
   bolt-on audit).
   → **Principle: production profiles default secure cookies / HSTS /
   HTTPS-redirect ON; development relaxation is explicit and
   compile-time-visible.** Maps directly onto primavera's frozen/profile
   config model — the deploy checklist disappears into the build profile's
   type.
   [Django 6.0 settings ref + security topic]

## Things to IMPROVE ON (they got it right; better-than-parity)

7. **ASP.NET's single policy primitive for ALL authorization** — roles and
   claims are both implemented on requirement + handler + policy; policies
   are reusable, testable, decoupled from routing (imperatively invocable
   via `IAuthorizationService`); combinators are explicit (requirements AND
   within a policy; multiple handlers OR per requirement; `context.Fail` as
   veto); evaluation is default-closed (silence ≠ success). One footgun:
   `InvokeHandlersAfterFailure` defaults true.
   → **Better: adopt the single default-closed policy algebra as the ONLY
   authz primitive; make AND/OR/veto first-class typed expressions checked
   at compile time; post-denial handler execution opt-in per handler
   (audit/logging), not a global default.**
   [MS policies docs, aspnetcore-10.0; verified at source level]

8. **Django's secure-by-default request protections with honest escape
   hatches** — auto-escaping on by default (docs admit "not entirely
   foolproof": unquoted-attribute injection; `mark_safe`/`safe` flagged);
   CSRF on for every POST (`csrf_exempt` is the documented weakening
   point); ORM parameterization by construction (`raw()`/`extra()` hand
   escaping back to the developer — and parameterization covers *values*,
   not identifiers: cf. CVE-2024-42005, CVE-2025-57833 in alias positions).
   → **Better: default-on everywhere, but make escape hatches TYPED and
   auditable — an unsafe-HTML type, an unsafe-SQL capability that appears
   in signatures — and close the identifier-position gap Django's design
   leaves open.** (Ownership note: primavera's generated repositories +
   store-native `@Query` already avoid string-assembled SQL by design;
   keep it that way.)
   [Django 6.0 security topic; OWASP Django cheat sheet]

9. **Django's CSRF design — adopt nearly wholesale** — secret rotates on
   every login (session-fixation-style rotation built in); tokens masked
   with a fresh per-response random mask specifically against BREACH
   compression side-channels (only the unmasked secret is compared); HTTPS
   requests validate Origin against host + trusted origins, falling back to
   strict Referer when Origin is absent; no Referer checking on plain HTTP
   (unreliable there).
   → **Better: keep rotation/masking/Origin semantics; fix the documented
   DX cost (stale pre-login tabs) with a grace-window dual-secret
   validation; make the plain-HTTP gap moot by refusing non-HTTPS in
   production profiles (see #6).**
   [Django 6.0 CSRF reference]

10. **Cross-cutting** — the three findings above compose: primavera's
    security model should be *one* algebra (7), *uniformly* default-closed
    (5), over *typed* routes (2