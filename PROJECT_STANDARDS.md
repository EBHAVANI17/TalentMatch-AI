# ENTERPRISE MASTER SPECIFICATION & ARCHITECTURAL STANDARD
**Domain-Agnostic Web Application Blueprint & AI Production Guidelines**

---

## 1. Core Operating Philosophy: The Central Product Shell
The landing experience must act as the **central entry point and product shell**.
- All major product capabilities must be discoverable and accessible from this shell.
- Functionality is organized into intelligent modules, workspaces, drawers, modals, tabs, and contextual routes rather than creating one massive monolithic scrolling page.

```text
                           LANDING / PRODUCT SHELL
                                      │
               ┌──────────────────────┼──────────────────────┐
               ↓                      ↓                      ↓
          Solutions                Features              Resources
               │                      │
               ↓                      ↓
       Auth / OIDC (Google)    Interactive Preview
               │
               ↓
           ONBOARDING (Role & Tenant Configuration)
               │
               ↓
        ENTERPRISE WORKSPACE (Role-Based Dynamic Shell)
               │
   ┌───────────┼───────────┬───────────┐
   ↓           ↓           ↓           ↓
  Module A    Module B    Module C   Admin Tower
   │           │           │           │
   └───────────┴─────┬─────┴───────────┘
                     ↓
          API & Relational Store (RBAC Enforced)
```

---

## 2. Universal Discovery Framework
Every project starts with the single core question:
> **"What problem should this product solve, who are the primary users, and what should each user be able to accomplish from the moment they enter the landing experience until they complete their main workflow?"**

From this answer, derive:
`Roles` → `Modules` → `Permissions (RBAC)` → `Workflows` → `Database Schemas` → `APIs` → `UI Design Tokens` → `Landing Experience`.

---

## 3. Mandatory Design & Interface Standards
1. **Zero Emojis**: Strictly forbid emojis across UI, code strings, logs, and toasts. Use SVG icons (e.g., Lucide Icons) or styled CSS badges exclusively.
2. **Professional SVG Favicons**: Always embed high-definition, crisp SVG vector icons in the document `<head>`.
3. **Typography & Layout Resilience**:
   - Modern typography scales (`Outfit`, `Plus Jakarta Sans`, `JetBrains Mono`).
   - Action buttons and tags must enforce `white-space: nowrap !important;` with appropriate flex/grid layouts so text never wraps vertically character-by-character.
4. **Design Tokens & Dark/Light System**:
   - Curated HSL/Hex color palettes with glassmorphism and subtle background depth.
   - Micro-animations must respect `prefers-reduced-motion`.

---

## 4. Security, Authentication & Multi-Tenancy
- **Google OAuth / OIDC & Credentials**: Secure token verification and session management via environment variables. Never hardcode credentials in frontend code.
- **RBAC Matrix**: Permissions enforced on backend API routes as well as frontend views (`create`, `read`, `update`, `delete`, `manage_users`, `view_audit_logs`).
- **Tenant Isolation**: Multi-tenant database schemas with strict organization-level scoping.
- **Tamper-Evident Audit Logging**: Every critical action (`Who`, `What`, `When`, `Target ID`, `IP Address`) recorded to the audit log.

---

## 5. Master Prompt Template (For AI Builders)

```text
Act as a world-class multidisciplinary product team consisting of:
1. Senior Product Architect
2. Enterprise UX/UI Designer
3. Design System Architect
4. Senior Frontend Engineer
5. Senior Backend Engineer
6. Database Architect
7. Authentication & Security Engineer
8. DevOps / Cloud Engineer
9. QA / Test Automation Engineer
10. Accessibility Specialist
11. SEO Specialist

I want you to design and build a COMPLETE PRODUCTION-READY ENTERPRISE-LEVEL WEB APPLICATION.
Do NOT treat this as a simple landing-page design project.

The LANDING EXPERIENCE must act as the central entry point and product shell:
Landing experience → Authentication → Onboarding → Product workspace → Domain modules → User workflows → Admin → Database → APIs → Security → Notifications → Analytics → Error handling → Testing.

[INSERT PROJECT INPUT HERE: Product Name, Domain, Target Users, Core Problems, Main Workflows, Brand Requirements]
```
