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

---

# Part 2 — Compile-time DI: what you give up (and what's free)

Second verified survey (2026-07-19) of what Micronaut, Quarkus/ArC,
Dagger-Hilt, and Spring-AOT/GraalVM concretely **sacrificed** by moving DI
from runtime reflection to build-time codegen — and which sacrifices bite
primavera given its constraints. Facts are 3-0 unanimous against primary
sources (GraalVM reference manual, Quarkus guides, Dagger/Hilt dev guides);
the FREE-vs-REAL mapping is *reasoned synthesis, not source-asserted* — treat
it as a recommendation.

> **Scope honesty.** The surviving evidence skews to **GraalVM + Quarkus +
> Dagger/Hilt**. Micronaut's `BeanDefinition` model and Spring-AOT's
> `BeanFactoryInitializationAotProcessor` were in the brief but produced no
> primary-sourced surviving claims — their specifics are inferred by analogy
> and should be confirmed before relying on them. Hot-reload and
> generated-code-debugging DX costs are under-evidenced here.

## The headline: most of the cost is already sunk

Every compile-time-DI sacrifice traces to **one** root — GraalVM's
closed-world assumption (all reachable code known at build time; no runtime
bytecode/class loading; unreached code DCE'd) plus each framework's
build-time graph freeze. [GraalVM metadata][g1], [Quarkus native tips][qn]
The decisive result for primavera: **most of these sacrifices are FREE** — a
borrow-checked, zero-reflection, fibers-only, DCE-for-embedded language was
never going to support the dynamic patterns being given up, so it inherits
the wins (fast startup, small image, **no reflection attack surface**)
without a real loss.

### Free sacrifices (primavera loses nothing — it forbade these already)

| Sacrificed capability | Why it's free for primavera |
|---|---|
| **Runtime class loading / closed-world** | Embedded + DCE targets *demand* closed-world; it's the goal, not a cost. [GraalVM compat][g2] |
| **Reflective interop** (serialization, reflective frameworks) | Zero runtime reflection by design. [GraalVM reflection][g3] |
| **Reachability-metadata maintenance burden** (hand-written JSON per app *and* per dependency — GraalVM's most-cited DX pain, severe enough to spawn a shared-metadata repo) | *Zero* — nothing to declare if there's no reflection. This is a **strategic win**, not a wash: the incumbents' worst DX tax simply doesn't exist. [GraalVM shared metadata][gm] |
| **Runtime dynamic proxies** | Fibers-only async already rules out the async/lazy-proxy patterns; ownership resists proxy-wrapper aliasing. [GraalVM proxy][g4] |

### The one corollary OBLIGATION the free list creates

Because primavera **cannot fall back on reflection**, it must **generate
serialization/introspection at compile time** — exactly what Micronaut
(`@Introspected`) and Quarkus do. This is not optional: it's the price of
the zero-reflection win, and it's already implied by the Data spec's
"AoT-generated binders, no reflection" and the config spec's generated
binders. Flag: audit that every place the spec assumes introspection (serde,
config binding, repository mapping, `@Entity` field access) has a
compile-time generation story, since there is no runtime escape hatch.

## The three REAL sacrifices (each needs a design answer)

The AOT frameworks already proved the recovery patterns; primavera should
adopt the *better* of each.

### R1. Test-double injection into a frozen graph — the deepest one
Every framework built explicit machinery because the graph is fixed at build
time. Dagger uses a **separate per-environment test component** that installs
fake modules, and **forbids** `@Provides` override via subclassing (brittle,
can't change graph shape). Hilt adds `@BindValue`, `@UninstallModules`,
`@TestInstallIn`. Quarkus adds `QuarkusMock`/`@InjectMock`. But the recovery
stays **awkward in version-specific ways**: `QuarkusMock` can't mock
`@Singleton`/`@Dependent` (only normal-scoped) beans; Hilt's per-test
overrides regenerate a whole component and hurt build speed; DCE causes
false-positive wiring failures (Quarkus ArC removes unused beans and "can't
detect programmatic lookup via `CDI.current()`", forcing `@Unremovable`).
[Dagger testing][dt], [Hilt testing][ht], [Quarkus mocking][qm]

> **primavera answer.** We already shipped the seam: **seed the scope with
> the double under the real key before the code under test runs**
> (`PrimaveraTest.request`/`freshSession` + `RequestScope.store`;
> `materialize`'s has-check short-circuits the real factory), plus
> cajeta-unit `TestContext` for `@Inject` overrides. This sidesteps the
> incumbents' worst problems by construction: no graph regeneration per test
> (scopes are runtime stores, not build-frozen components → no Hilt-style
> build-speed hit), and **no scope-class exclusions** (the ownership model
> makes any scoped bean seedable, dodging QuarkusMock's `@Singleton` gap).
> The design task remaining: a first-class override API over `TestContext`
> for *singleton*-scoped collaborators, and DCE must not remove a bean solely
> because only tests inject it (the ArC false-positive class — our
> reflection-registry-free model may avoid it, but verify).

### R2. Runtime conditional / environment-varying wiring
Classic DI decided `@ConditionalOnX` at runtime; AOT frameworks resolve
conditions at **build time**. Quarkus's `@IfBuildProfile`/`@IfBuildProperty`
have "absolutely no effect" from runtime profile/property changes.
[Quarkus CDI][qc] This is REAL: an enterprise app that picks an
implementation from a runtime env var expects that to work.

> **primavera answer.** Split the concern the incumbents conflate.
> **Graph shape** (which implementations exist) is a build-time decision —
> deployment profiles (§3.6), the `@Profile`/seam mechanism we already use
> for logging appenders. **Value selection** (which of the compiled-in
> implementations a request uses) is a runtime decision expressed as
> ordinary strategy-selection over the DI-provided set (`@Inject List<A>`
> multibinding + a runtime selector), **not** as graph mutation. Open
> question the spec should resolve: is there a residuum of genuinely
> runtime-*shape* needs that this can't serve? (research open-Q).

### R3. Plugin / runtime-extension architectures
CDI Portable Extensions (the runtime SPI for third parties to register
beans) "cannot be supported" under build-time DI and must be reimplemented
as **build-time extensions**; no bytecode-loading-at-runtime plugin system
works under closed-world. [Quarkus CDI][qc], [GraalVM compat][g2] Partly
mitigated by primavera's own constraints (a plugin that ships owned,
borrow-checked code can't be loaded from bytecode at runtime anyway).

> **primavera answer.** Build-time extension points only — the
> annotation-processing/codegen seam the plan already reserves ("lets
> primavera or any framework plug its policy into the compiler"). Third-party
> capability arrives as a **compiled dependency wired into the graph at
> build**, not a runtime-registered bean. This is a real constraint to
> *document as a boundary*, not a gap to close: "no runtime plugin
> registration" is a deliberate posture, consistent with DCE/embedded.

## Where compile-time DI clearly WON (keep these as the payoff)
Fast startup, low memory, small native-image size, and — most relevant to
Part 1 — a **near-zero reflection attack surface**. primavera gets all four
by construction; Part 1's security argument and Part 2's zero-metadata win
are the same property viewed from two sides.

## Open questions (unverified)
1. Micronaut `@Introspected` / Spring-AOT introspection APIs vs. what
   primavera needs for reflection-free serde — confirm from primary sources.
2. Quantify the WIN magnitude (startup ms, RSS, image bytes) so the payoff is
   measured, not just asserted.
3. Forbid programmatic bean lookup (`CDI.current()`-style) outright — which
   kills the DCE false-positive class — or allow it with explicit
   reachability marking? (We already have `materialize`/`lookup`, a *scoped*
   programmatic lookup — decide whether that's the only sanctioned form.)
4. Is there an enterprise use case needing runtime graph-*shape* decisions
   that R2's strategy-selection genuinely cannot serve?

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
[g1]: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
[g2]: https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/
[g3]: https://www.graalvm.org/jdk21/reference-manual/native-image/dynamic-features/Reflection/
[g4]: https://www.graalvm.org/22.1/reference-manual/native-image/DynamicProxy/
[gm]: https://medium.com/graalvm/enhancing-3rd-party-library-support-in-graalvm-native-image-with-shared-metadata-9eeae1651da4
[qn]: https://quarkus.io/guides/writing-native-applications-tips
[qc]: https://quarkus.io/guides/cdi-reference
[qm]: https://quarkus.io/blog/mocking/
[dt]: https://dagger.dev/dev-guide/testing.html
[ht]: https://dagger.dev/hilt/testing.html
