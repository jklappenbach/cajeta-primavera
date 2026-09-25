# Roadmap

primavera's roadmap lives on the agents convention in the cajeta repo, not
here. The spec is `specs/primavera-web-spec.md` and the plan is
`agents/primavera-web-plan.md` in that repo. Completion lives in the plan's
checkboxes.

What the two documents that used to sit here still had open moved into that
plan's Unit 0: the once-guard on lazy static init, the static-field
method-receiver workaround check, wiring `@Component` allocation modes to the
scoped accessor pair, and the DI test-enablers' `@Mock` codegen hook. The
shipped phases (request scope, session scope, test helpers) are recorded in
the git history of the removed files.
