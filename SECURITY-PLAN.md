# Security Plan — Flowgate

**Status:** Design
**Owner:** Founder
**Last updated:** 2026-09-23

This document is the security and compliance roadmap for Flowgate. It is
honest about what is built today versus what is planned, so the same
answer can be given to a design partner, an investor, or a security
reviewer.

---

## What we have today

- **Authentication:** shared API key via `A27_API_KEYS` env var
  (comma-separated allowlist). Fails closed — an empty allowlist answers
  503, never 200.
- **Per-deployment isolation:** one deployment per customer. One Postgres
  database per customer (Neon or Render). One uploads directory per
  customer on the Render persistent disk.
- **Immutable event ledger:** every business decision (document
  processed, rule evaluated, proposal approved, capital call reviewed)
  is written to `ledger_entries` with a `trace_id`. Events are
  append-only — no update or delete path in the ORM.
- **Secrets:** stored in Render environment variables, never in the
  repository. `render.yaml` uses `sync: false` for keys.
- **Transport:** HTTPS via Render's proxy. No plaintext HTTP in
  production.
- **No stored passwords:** the system has never asked for or stored a
  password. Identity is currently a shared key.
- **ORM-enforced no-self-certification:** `app/models/orm.py` blocks any
  system write to a human-only status (`scholar_approved`,
  `scholar_rejected`). Only the review path can write those values, and
  it requires a named reviewer.

## What we do not have

- Per-user identity. One shared key grants full access to everyone.
- Roles. Anyone with the key can do anything.
- Admin action audit trail. Business events are logged; user management,
  rule edits, and login attempts are not.
- Multi-tenancy. Every deployment serves exactly one customer.
- SSO (SAML, OIDC).
- SOC 2 or ISO 27001 certification.
- A written incident response process.
- A data processing agreement template.

---

## The trust question

Any regulated buyer — fund administrator, Islamic bank, family office —
will ask five questions in the same order:

1. How do we authenticate our users?
2. Who can see what?
3. Do you support SSO?
4. Do you have SOC 2?
5. What is your incident response process?

Questions 1–3 are code. Questions 4–5 are process and paperwork. Both are
required, but only one of them is on the critical path to a first pilot.

---

## Roadmap

### Phase 1 — Per-user identity (2–3 weeks)

Replace the shared API key with per-user login. Do not build password
handling ourselves. Use a managed identity provider (Clerk, Supabase
Auth, or similar).

Scope:

- Sign-up, sign-in, sign-out, password reset, email verification:
  handled by the provider.
- Backend verifies JWTs issued by the provider on every request.
- API key path preserved as a secondary mechanism for programmatic
  access (CI, scripts, webhooks).
- New `users` table: `id`, `email`, `name`, `role`, `created_at`,
  `last_login_at`, `external_auth_id`.

### Phase 2 — Role-based access control (1 week)

Four roles. No more.

| Role | Can do | Cannot do |
|---|---|---|
| `admin` | Manage users, API keys, settings | — |
| `compliance_officer` | Edit rules, review findings, review documents | Manage users |
| `reviewer` | Approve proposals, approve capital calls, submit human reviews | Edit rules, manage users |
| `viewer` | Read-only access to everything | Any write |

This maps directly to how private capital firms staff:

- Shariah board member → `reviewer` (approves, does not edit)
- Junior analyst → `viewer`
- Head of compliance → `compliance_officer`
- GP or operations lead → `admin`

The mapping is not arbitrary. It matches the review gates the product
already enforces (named reviewer required for approvals).

### Phase 3 — Admin action audit log (few days)

Every administrative action writes to the existing ledger table, same
immutability, same `trace_id`:

- `user.created` / `user.role_changed` / `user.deactivated`
- `api_key.created` / `api_key.revoked`
- `login.success` / `login.failure` (with source IP)
- `rule.created` / `rule.deactivated`
- `settings.changed`

This is the single artifact SOC 2 auditors care most about. The ledger
already exists; the work is routing admin events into it.

### Phase 4 — Multi-tenancy (2–3 weeks)

**Do not build this yet.** Build it when a design partner explicitly
asks to share infrastructure across multiple customers.

Until then, one deployment per customer is a *stronger* security story,
not a weaker one: no shared tables, no row-level security policies to
misconfigure, no cross-tenant leak surface. A single-tenant deployment
is the honest answer to a security questionnaire.

### Phase 5 — Certifications

| Certification | Cost | Time | When to start |
|---|---|---|---|
| SOC 2 Type I | $15–40K | 3–6 months prep | When a customer requires it in a signed MSA |
| SOC 2 Type II | $30–100K total | 6–12 months (observation window) | After Type I, when the same customer still requires it |
| ISO 27001 | $20–60K | 6–9 months | If the first regulated customer is in GCC or Malaysia |

**Automation platforms:** Vanta or Drata, $10–25K/year. They collect
60–70% of the evidence automatically and save roughly 200 hours of
spreadsheet work. Buy on day one of prep, not before.

**Do not begin SOC 2 prep at seed stage.** It burns 4–6 months and
$20–40K on a certificate no design partner will require until they are
signing a contract. The moment it becomes a customer-acquisition cost is
the moment to start.

---

## Third-party data flows

Document text is sent to OpenRouter, which routes to an upstream model
provider (Nvidia, Google, Meta, and others depending on availability).
This is unavoidable for the LLM extraction path.

**There is no zero-retention agreement in place with OpenRouter today.**

For regulated customers, three options exist:

1. **OpenRouter zero-retention endpoint** — available on paid tiers.
   Add when a customer requires it.
2. **Self-hosted open-weights model** — deploy a small model
   (Llama 3.x, Qwen 2.5) on the same infrastructure. Highest control,
   adds ops burden.
3. **Per-customer LLM key** — the customer provides their own OpenRouter
   key, their data goes through their account, their terms apply.

For a seed-stage pitch, name this honestly. It is a real limitation, not
a fatal one. Most design partners will accept it if the alternative is
"the whole feature doesn't exist."

---

## Data handling

- **Storage:** all customer data lives in the customer's own Postgres
  database. No cross-customer data mixing.
- **Backups:** Render disk snapshots + Neon point-in-time recovery.
  Retention: per provider defaults.
- **Deletion:** on customer request, drop the database and the uploads
  directory. No soft-delete of customer data.
- **Analytics:** none. Document content is never sent to analytics
  vendors.
- **Access logs:** HTTP access logs on Render, 30-day retention.
- **Business events:** in Postgres, permanent (the ledger is the audit
  trail).

---

## What is honest to say at seed stage

> "We have per-user auth and role-based access built. Every admin action
> is logged to the immutable ledger. SOC 2 Type I is planned for Q2 of
> next year, funded from this round, gated on a design partner requiring
> it. Auditor shortlist is Vanta and Prescient Assurance."

This is a real answer. It shows the market is understood and the plan is
concrete. It does not pretend the certificate already exists.

## What NOT to say

- *"We'll do SOC 2 when we need to."* — reads as naive about the market.
- *"SOC 2 is a distraction at seed."* — dismissive of the buyers you
  are selling to.
- *"We're almost SOC 2 compliant."* — no one is "almost" without an
  auditor. This reads as either confused or dishonest.

---

## Immediate actions

**This week:**

- Add per-user authentication (Clerk or Supabase Auth).
- Implement three roles: `admin`, `reviewer`, `viewer`.
- Route login and admin events into the existing ledger table.

**Next month:**

- Login UI polish, email verification flow, password reset flow.
- API key management UI (generate, label, revoke).
- User management UI (invite, change role, deactivate).
- `SECURITY.md` — public-facing summary for the website.

**When a customer asks:**

- Engage Vanta.
- Begin SOC 2 Type I prep.
- Draft a DPA template.
- Add the security questionnaire answer pack to the sales assets.

---

## The line to hold

Flowgate never certifies compliance on its own. The ORM blocks system
writes to human-only statuses. The assistant never says "this is
compliant." Only a human reviewer does. That invariant is structural, not
policy — it holds under any future feature, any customer, any
configuration.

The same discipline applies to security: no claim is made that cannot be
traced to code, a policy, or a signed certificate.
