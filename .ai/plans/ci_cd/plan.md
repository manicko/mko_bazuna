# CI/CD Implementation Plan for Mko Bazuna

**Date:** 2026-07-27  
**Based on:** `.ai/plans/ci_cd/research.md`  
**Strategy:** Docker-based manual deploy with GitHub Actions

---

## 1. Overview

Implementation of Docker-based CI/CD pipeline with manual deployment to VPS via GitHub Actions. Architecture:
- **CI:** Parallel lint → typecheck → test jobs on push/PR
- **CD:** Manual workflow dispatch → build → push → deploy
- **Registry:** GitHub Container Registry (GHCR)
- **Target:** Single VPS (4 CPU, 8 GB RAM), no staging environment

---

## 2. Pre-implemented Components

| Component | Status | Notes |
|-----------|--------|-------|
| Non-root user (uid 1000) | ✅ Already in Dockerfile | See docker/Dockerfile |
| Coverage upload | ✅ Already configured | CI workflow |
| PostgreSQL 18 service | ✅ Already configured | CI workflow |
| Build cache (registry) | ✅ Partial | Currently uses registry cache; migrate to GHA cache |

---

## 3. Implementation Stages

### Stage A: Preparation & Setup (Priority: HIGH)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| A1 | Create `production` environment in GitHub repository settings | HIGH | trivial | None | Deployment could run without proper approval |
| A2 | Add GitHub Secrets: SERVER_HOST, SERVER_USER, SERVER_SSH_KEY, SERVER_PORT | HIGH | trivial | A1 | Secret exposure if not properly configured |
| A3 | Add GitHub Secrets: DJANGO_SECRET_KEY, BOT_TOKEN, ADMIN_PASSWORD, POSTGRES_PASSWORD | HIGH | trivial | A1 | Secret exposure if not properly configured |
| A4 | Prepare VPS directory structure (`/opt/mko_bazuna/{backups,certs,media}`) | HIGH | small | None | Security misconfiguration, permission issues |
| A5 | Create deploy user on VPS with Docker group membership | HIGH | small | A4 | Security misconfiguration, permission issues |
| A6 | Clone repository to VPS and create `.env.docker` file | HIGH | small | A5 | Secret exposure if copied incorrectly |
| A7 | Set file permissions on VPS (600 for .env.docker, deploy ownership) | MEDIUM | trivial | A6 | Secret exposure in logs |

---

### Stage B: CI Pipeline (Enhancement)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| B1 | Add concurrency control to existing `.github/workflows/ci.yml` | MEDIUM | trivial | None | Resource waste on multiple concurrent builds |
| B2 | Rename/move `ci.yml` to `ci-cd.yml` and add workflow_dispatch trigger | HIGH | small | B1 | Broken workflow if not done carefully |
| B3 | Add path filters to skip CI for docs-only changes | LOW | small | B1 | CI might run unnecessarily, consuming minutes |
| B4 | Verify existing PostgreSQL 18 service configuration | HIGH | trivial | None | — |
| B5 | Verify coverage artifact upload configuration | LOW | trivial | None | — |

---

### Stage C: CD Pipeline (Extend existing)

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| C1 | Add GHCR authentication to existing build job | HIGH | small | B1 | Authentication failures |
| C2 | Update build job to push images with SHA-based tags | HIGH | small | C1 | Failed image pushes |
| C3 | Add GHA layer caching to build step | MEDIUM | small | C2 | Slow builds without caching |
| C4 | Implement deploy job with SSH-based Docker Compose orchestration | HIGH | medium | A2, A3, C2 | Production outage, failed rollbacks |
| C5 | Add deploy health check with retry loop (30 attempts, 5s delay) | HIGH | trivial | C4 | Failed deployments going unnoticed |
| C6 | Add workflow_dispatch inputs for image tag selection (rollback support) | MEDIUM | small | C2 | Wrong image deployed |

---

### Stage D: Security & Hardening

| ID | Task | Priority | Effort | Dependencies | Risks |
|----|------|----------|--------|--------------|-------|
| D1 | Add Trivy security scan job (CRITICAL/HIGH severity, non-blocking) | MEDIUM | small | C2 | Unpatched vulnerabilities in production |
| D2 | Configure Trivy SARIF upload to GitHub Security tab | MEDIUM | trivial | D1 | No security visibility |
| D3 | Add dependency audit (pip-audit) for Python packages | MEDIUM | small | None | Outdated/vulnerable packages |
| D4 | Document rollback procedure in `docs/ops/deployment.md` | MEDIUM | small | C4 | Undocumented recovery procedures |

---

## 4. Execution Order (Topological Sort)

```
A1 → A2, A3 → A4, A5, A6, A7
             ↓
B1 → B2 → B3, B4, B5
         ↓
C1 → C2 → C3 → C4, C5, C6
         ↓
D1 → D2
D3 → (after C2)
D4 → (after C4)
```

**Critical Path:** A1 → A2/A3 → B1 → C1 → C4 (sequential, ~5-7 days calendar time with parallel execution)

---

## 5. Task Graph (Dependency DAG)

```
┌─────────────┐
│     A1      │ (GitHub Environment)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A2, A3      │ (GitHub Secrets)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ A4, A5, A6 │ (VPS Setup)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Stage B: CI Enhancements   │
├────────┬────────┬──────────┤
│   B1   │   B2   │ B3, B4, B5│
│Concurrency│ Rename  │ Verify   │
└────────┴────────┴──────────┘
                     │
                     ▼
┌──────────────────────────────────────────┐
│        Stage C: CD Pipeline               │
├────────┬────────┬──────────┬────────────┤
│   C1   │   C2   │    C3    │ C4, C5, C6 │
│  GHCR  │ Push   │ Caching  │ Deploy     │
└────────┴────────┴──────────┴────────────┘
                     │
                     ▼
┌─────────────────────────────┐
│ Stage D: Security Layer     │
├────────┬────────┬──────────┤
│   D1   │   D2   │   D3     │
│ Trivy  │ SARIF  │ Audit    │
└────────┴────────┴──────────┘
         │
         ▼
┌─────────────┐
│     D4      │
│  Documentation│
└─────────────┘
```

---

## 6. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit exceeded | MEDIUM | HIGH | Implement path filters; optimize test duration; consider public repo |
| SSH key compromise | LOW | HIGH | Use ED25519 keys; rotate quarterly; restrict deploy user permissions |
| Trivy scan blocks deploy | LOW | MEDIUM | Run as non-blocking job; use `ignore-unfixed: true` |
| Database migration failure | MEDIUM | HIGH | Advisory lock prevents concurrent runs; test migrations in CI; backup before deploy |
| Rollback procedure failure | LOW | MEDIUM | Document; test with known-good SHA tag |
| Secret leak in logs | LOW | CRITICAL | Mask secrets with `::add-mask::`; use GitHub Environments |

---

## 7. Verification Steps

After implementation:

1. **CI Verification:**
   - Push to `develop` branch → verify CI runs (no build/deploy)
   - Push to `main` branch → verify all jobs execute in parallel
   - Open PR → verify CI runs with same behavior as push

2. **CD Verification:**
   - Run workflow dispatch with empty tag → latest `main` image deploys
   - Verify health check passes after deployment (30 attempts × 5s)
   - Verify containers running: `docker compose ps` on VPS

3. **Rollback Verification:**
   - Trigger deploy with specific SHA tag
   - Verify old version is pulled and running

---

## 8. Files to Create/Modify

| Action | Path |
|--------|------|
| Rename & Modify | `.github/workflows/ci.yml` → `ci-cd.yml` (add workflow_dispatch, concurrency, CD jobs) |
| Create | `docs/ops/deployment.md` (rollback procedure, deployment guide) |

### 8.1 Deployment Commands Reference

The deploy job will execute on VPS:
```bash
cd /opt/mko_bazuna

# Pull latest images
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Stop old containers gracefully
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop

# Remove old containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f

# Start new containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images
docker image prune -f
```

---

## 9. Effort Summary

| Effort | Tasks Count |
|--------|-------------|
| trivial | A1, A2, A3, A7, B1, B4, B5, C5, C6, D2 |
| small | A4, A5, A6, B2, B3, C1, C2, C3, D1, D3, D4 |
| medium | C4 |

**Total: 22 tasks** — Estimated effort: **large** (~5-7 days with validation)

---

## 10. Estimated Timeline

| Stage | Tasks | Calendar Time |
|-------|-------|-------------|
| A: Preparation | A1-A7 | 1 day |
| B: CI Enhancement | B1-B5 | 1 day |
| C: CD Extension | C1-C6 | 2-3 days |
| D: Security | D1-D4 | 1 day |
| **Total** | **22 tasks** | **5-7 days** (with testing/validation) |