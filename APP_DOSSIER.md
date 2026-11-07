# ARTHUR — Project Dossier & Ownership Document

**Document type:** Official product record
**Owner / Creator:** Mohammed Farhan
**Project:** ARTHUR (Autonomous Reasoning & Task Handling Utility Runtime)
**Version:** MVP 1.0
**Date:** September 29, 2026

---

## 1. Creator & Ownership

- **Created, designed, and owned by:** Mohammed Farhan 
- **Role:** Sole Owner and sole Administrator of the ARTHUR system and mobile app.
- Farhan is the originator of the ARTHUR concept, architecture, feature set, security model, and product vision.
- All intellectual property, source code, branding, and data in this project belong to Farhan.

## 2. What ARTHUR Is

ARTHUR is a futuristic personal and team AI agent platform — far more than a chatbot. It works as a personal AI teammate, project manager, developer, researcher, and 24/7 autonomous worker.

The user speaks to ARTHUR naturally (text, voice planned), and ARTHUR:

1. Understands the objective
2. Asks only necessary clarifications
3. Breaks it into smaller tasks
4. Creates a project plan
5. Assigns specialized AI agents
6. Executes with real tools
7. Monitors progress
8. Tests the work
9. Detects and fixes errors
10. Retries failures
11. Remembers everything important
12. Works while the owner is offline
13. Asks for approval when required
14. Notifies on completion
15. Delivers a final report

## 3. System Architecture

```
USER / TEAM
  → Web App / Mobile App / Voice
    → ARTHUR CORE (Manager Agent)
      → PLANNER → TASK QUEUE → SPECIALIZED AGENTS
        → TOOLS / APIs / COMPUTER / FILES
          → MEMORY + DATABASE
            → TESTING + MONITORING → RETRY / RECOVERY → COMPLETION
```

## 4. Specialized Agents

| Agent | Responsibility |
| --- | --- |
| Manager | Coordination, planning, delegation, monitoring, recovery, approvals, completion verification |
| Researcher | Web research, documentation, comparisons, sources, summaries |
| Developer | Code writing, file editing, Python/terminal, debugging, tests, Git/GitHub, APIs |
| QA | Testing, bug hunting, requirement checks, failure reports back to Developer |
| Browser | Web navigation, forms, downloads, web-app workflows |
| Analyst | CSV/Excel, statistics, reports, dashboards |

Planned: Design, DevOps, Content, Marketing, Finance, Documentation, Security agents.

## 5. Task Engine (24/7 Autonomous)

- Persistent SQLite-backed task queue — no infinite LLM loops; workers wake when tasks need execution.
- Task states: CREATED → PLANNING → QUEUED → RUNNING → TESTING → COMPLETED, with WAITING\_FOR\_TOOL, WAITING\_FOR\_APPROVAL, FAILED, RETRYING.
- Checkpoints after every step; crash recovery resumes from the last successful step.
- Bounded retries with exponential backoff; failure analysis and auto-fix loop.
- Explicit per-project completion conditions, verified before a project is marked COMPLETED.

## 6. Memory System

- Short-term conversation memory
- Long-term user memory
- Project memory (stack, tasks, bugs, team)
- Team memory
- Task history and tool execution history
- Documentation / knowledge memory
- Agent execution logs
- All persisted in the database — never only in conversation context.

## 7. Data & Database

Structured tables: users, teams, team\_members, projects, tasks, agents, agent\_runs, messages, memories, documents, tools, tool\_permissions, approvals, activity\_logs, push\_tokens.

- **MVP storage:** SQLite (zero-cost, file-permission hardened).
- **Growth path:** PostgreSQL + pgvector (semantic memory) + Redis (cache/queues), via Docker Compose profiles.
- **User rights built in:** one-tap full data export (JSON) and full account deletion (cascade across all tables).

## 8. Security Model

- **Sole administrator:** Mohammed Farhan is the ONLY admin. No other admin accounts exist — no defaults, no backdoors, no system/agent admins.
- **No self-promotion:** only the owner can grant or revoke roles.
- **App self-protection:** agents cannot modify ARTHUR's own code, configuration, roles, or permissions without explicit owner approval.
- **Permission levels:** L0 READ → L1 LOW RISK → L2 EXTERNAL ACTIONS → L3 HIGH RISK (always requires explicit human approval).
- **Secrets:** encrypted at rest; automatic log scrubber redacts key-like values from logs, chat, and errors.
- **Egress control:** agents cannot send user data to external services without approval; unknown destinations denied by default.
- **Auth:** bcrypt password hashing, expiring session tokens, rate-limited logins with lockout.
- **Audit:** every role change, permission change, tool call, and approval is logged with actor and timestamp.
- **Transport/app:** security headers, CORS restrictions, input validation on all endpoints.

## 9. Privacy

- Store-ready Privacy Policy included (`PRIVACY_POLICY.md`).
- Data collected: account info, project/task content, usage logs, push tokens, device info — each with stated purpose.
- No sale of data; user data never leaves the system without owner approval.
- User rights: access, export, correction, deletion.
- Privacy-policy public URL prepared for App Store / Play Store submission.

## 10. Admin Information

| Field | Value |
| --- | --- |
| Administrator name | Mohammed Farhan |
| Role | Owner (sole admin) |
| Admin powers | Full: user management, role assignment, approval of all levels incl. L3, security configuration, data export/deletion |
| Admin restrictions | None — all app modifications are under the owner's control |

## 11. Mobile App (iOS & Android)

- **Framework:** Expo + React Native + TypeScript (single codebase, both stores).
- **App name:** ARTHUR — `com.arthur.ai`
- **Screens:** Chat, Dashboard (status/projects/agents/tasks), Approvals (one-tap approve/deny), Projects & task detail.
- **Push notifications:** Expo Push — approval requests, task failures, project completion.
- **Branding:** official ARTHUR "A" logo (app icon, adaptive icon, splash screen).
- **Publishing:** EAS Build; Apple Developer and Google Play Console accounts required (owner-held); publish guide in `mobile/README.md`.

## 12. Web Dashboard

Single-file futuristic dashboard (`frontend/dashboard.html`): online status, projects, active agents, running tasks, progress bars, queue, approvals, logs, and chat — served by the FastAPI backend.

## 13. Tech Stack

Python, FastAPI, Pydantic · SQLite (Postgres/pgvector/Redis later) · Expo / React Native / TypeScript · Docker Compose · Playwright & MCP (automation path) · OpenAI-compatible LLM interface with offline demo mode.

## 14. Development Roadmap (Creator's Plan)

1. Core Python agent → 2. Tools → 3. Autonomous execution loop → 4. Specialized agents → 5. Persistent memory → 6. 24/7 worker system → 7. Dashboard → 8. Browser/computer control → 9. Team collaboration → 10. Voice → 11. Cloud deployment.

## 15. Ownership Statement

ARTHUR — its concept, design, architecture, security model, mobile app, branding, and all associated materials — was created by and belongs exclusively to M**ohammed&#32;**Farhan is the sole administrator and final authority over every aspect of the system.

---

*End of dossier.*