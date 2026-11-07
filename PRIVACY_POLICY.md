# Privacy Policy — ARTHUR

**Effective date:** October 1, 2026
**Operator:** [APP OPERATOR] ("we", "us")
**Contact:** [CONTACT EMAIL]

ARTHUR ("Autonomous Reasoning & Task Handling Utility Runtime") is a personal
AI agent system: it plans and executes software-project tasks on your behalf
through a chat interface, a web dashboard, and the ARTHUR mobile app (iOS and
Android). This policy explains what data we collect, why, and what rights you
have. It applies to the ARTHUR backend service, the web dashboard, and the
mobile app.

By using ARTHUR you agree to the collection and use of information described
below. If you self-host ARTHUR, **you** are the operator of your instance and
this policy describes how the software handles data on your behalf.

---

## 1. Data we collect

| Category | What | Purpose |
|---|---|---|
| **Account info** | Username, role, bcrypt password hash, session metadata (creation/expiry, revocation) | Authentication, access control, security |
| **Project & task content** | Project names/descriptions, task titles, steps, results, completion criteria, checkpoints | Core function: planning and executing your goals |
| **Chat & conversation history** | Messages you send and ARTHUR's replies | Continuity of work, context for the agent |
| **Files & documents you create** | Files ARTHUR writes into your project workspaces (code, notes, READMEs) | Deliverables you asked ARTHUR to produce |
| **Usage & audit logs** | Tool calls, timestamps, success/error records, login attempts (IP, time, outcome), approval decisions | Security monitoring, abuse prevention, debugging |
| **Push tokens** | Expo push tokens + platform (iOS/Android) | Delivering notifications you asked for (approvals, task results) |
| **Device info** | Platform string supplied at push registration (e.g. "ios"/"android") | Routing notifications to the right device |
| **Secrets you store** | API keys/tokens you save in ARTHUR's secret store | Stored **Fernet-encrypted at rest**; only used for the integrations you configure |

We do **not** collect advertising identifiers, precise location, contacts,
photos, or microphone/camera data. ARTHUR has no ads and no cross-app tracking.

## 2. Legal basis

- **Contract / legitimate interest:** operating the agent service you asked for
  (planning tasks, sending notifications you enabled).
- **Consent:** push notifications (you opt in on your device; you can revoke
  the OS permission at any time).
- **Legal obligation:** security logging needed to protect the service.

## 3. How data is stored & protected

- **Self-hosted by default.** The reference deployment stores everything in a
  local SQLite database on the operator's own machine/VPS. Nothing leaves
  that machine except the third-party transfers listed in §4.
- **Encryption at rest:** stored secrets (API keys/tokens) are Fernet-encrypted
  (AES-128-CBC + HMAC) with a key from `ARTHUR_SECRET_KEY`. The database file
  is created with `0600` file permissions.
- **Encryption in transit:** HTTPS/TLS for the API, dashboard, and mobile app
  in production (see "Hosting" below).
- **Authentication:** bcrypt password hashing, random 256-bit session tokens
  with expiry, login rate limiting (5 attempts/min/IP) and temporary lockout
  after repeated failures.
- **Least privilege:** agents run under permission levels 0–3; any high-risk
  action or any transmission of your data to an external service requires your
  explicit approval. The operator is the sole administrator.
- **Secret hygiene:** API keys and tokens are automatically redacted from logs,
  chat history, and error messages.

No method of transmission or storage is 100% secure, but we apply the measures
above and review them as the product evolves.

## 4. Third parties

Data leaves your ARTHUR instance only through these integrations, and only as
needed for the feature you use:

| Third party | Data shared | Why |
|---|---|---|
| **[LLM PROVIDER]** (e.g. OpenAI-compatible API; operator-configured) | Task prompts you submit (only when DEMO_MODE is off) | Generating plans and agent reasoning |
| **[HOSTING PROVIDER]** (operator's VPS/cloud) | All stored data (as the host of the instance) | Running the backend service |
| **Expo (Exponent)** | Push token + notification title/body you approved | Delivering push notifications via `exp.host` |

We do not sell your data. We do not share it with advertisers or data brokers.
An egress allowlist with default-deny blocks the app from sending your data to
any host you have not explicitly approved.

## 5. Data retention

- **Project/task/chat data:** kept until you delete it (per project or via
  account deletion).
- **Audit & login-attempt logs:** kept for security purposes; delete your
  account to remove entries tied to you.
- **Push tokens:** kept until you revoke notification permission, unregister
  the device, or delete your account.
- **Backups** (if the operator configures them) follow the operator's backup
  retention schedule.

## 6. Your rights

You have the right to **access**, **export**, **correct**, and **delete** your
data, and to **withdraw consent** (e.g. disable push notifications) at any time.

- **In the app/CLI:** use data export (JSON download of everything ARTHUR
  holds about you) and account deletion (cascade-deletes your profile,
  sessions, memberships, device tokens, and log entries tied to you).
- **By email:** contact [CONTACT EMAIL] and we will respond within 30 days.

Note: the operator/administrator account cannot delete itself while it is the
sole administrator (this protects the instance from being left ownerless).

## 7. Children's privacy

ARTHUR is not directed at children under 13 (or the minimum age in your
jurisdiction). We do not knowingly collect data from children. If you believe
a child has provided us data, contact [CONTACT EMAIL] and we will delete it.

## 8. International transfers

If you use a hosted instance, your data is processed where the operator hosts
it ([HOSTING REGION]). Transfers to the third parties in §4 occur only when
you enable those features and are protected by TLS and the safeguards those
providers publish.

## 9. Changes to this policy

We will update this policy as ARTHUR evolves. Material changes will be
announced in the app/dashboard and the "Changelog" below will be updated. The
effective date at the top always reflects the current version.

## 10. Contact

Questions about privacy, or to exercise your rights:

- Email: [CONTACT EMAIL]
- Operator: [APP OPERATOR]

---

## Changelog

- **2026-10-01** — Initial publication (v1.0): covers MVP data collection,
  encrypted secret storage, authentication, push notifications, and user
  data rights (export/deletion).
