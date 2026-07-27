# CI/CD Implementation Plan for Mko Bazuna

**Date:** 2026-07-27  
**Based on:** `.ai/plans/ci_cd/research.md`

---

## 1. Overview

Implementation of Docker-based CI/CD pipeline with manual deployment to VPS via GitHub Actions. Architecture:
- **CI:** Parallel lint → typecheck → test jobs on push/PR
- **CD:** Manual workflow dispatch → build → push → deploy
- **Registry:** GitHub Container Registry (GHCR)
- **Target:** Single VPS (4 CPU, 8 GB RAM), no staging environment

---

## 2. Implementation Stages

### Stage A: Preparation & Setup
Configure GitHub secrets, environments, and VPS prerequisites.
### Stage B: CI Pipeline
Implement quality gates and testing automation.
### Stage C: CD Pipeline  
Build, push, and deploy workflows with manual trigger.
### Stage D: Security & Hardening
Add vulnerability scanning and security best practices.

---

## 3. Task Breakdown

### Stage A: Preparation & Setup

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| A1 | Create `production` environment in GitHub repository settings | HIGH | trivial | None |
| A2 | Add GitHub Secrets: SERVER_HOST, SERVER_USER, SERVER_SSH_KEY, SERVER_PORT | HIGH | trivial | A1 |
| A3 | Add GitHub Secrets: DJANGO_SECRET_KEY, BOT_TOKEN, ADMIN_PASSWORD, POSTGRES_PASSWORD | HIGH | trivial | A1 |
| A4 | Prepare VPS directory structure (`/opt/mko_bazuna/{backups,certs,media}`) | HIGH | small | None |
| A5 | Create deploy user on VPS with Docker group membership | HIGH | small | A4 |
| A6 | Clone repository to VPS and create `.env.docker` file | HIGH | small | A5 |
| A7 | Set file permissions on VPS (600 for .env, deploy ownership) | MEDIUM | trivial | A6 |

### Stage B: CI Pipeline (Enhancement)

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| B1 | Add concurrency control to existing `.github/workflows/ci.yml` | MEDIUM | trivial | A1 |
| B2 | Rename/move `ci.yml` to `ci-cd.yml` and add workflow_dispatch trigger | HIGH | small | B1 |
| B3 | Add path filters to skip CI for docs-only changes | LOW | small | B1 |
| B4 | Verify existing PostgreSQL 18 service configuration (already correct) | HIGH | trivial | None |
| B5 | Verify coverage artifact upload configuration (already exists) | LOW | trivial | None |

### Stage C: CD Pipeline (Extend existing)

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| C1 | Add GHCR authentication to existing build job | HIGH | small | B1 |
| C2 | Update build job to push images with proper tags | HIGH | small | C1 |
| C3 | Add GHA layer caching to build step (replace registry cache) | MEDIUM | small | C2 |
| C4 | Implement deploy job with SSH-based Docker Compose orchestration | HIGH | medium | A2, A3, C2 |
| C5 | Add deploy health check with retry loop | HIGH | small | C4 |
| C6 | Add workflow_dispatch inputs for image tag selection | MEDIUM | small | C2 |

### Stage D: Security & Hardening

| ID | Task | Priority | Effort | Dependencies |
|----|------|----------|--------|--------------|
| D1 | Add Trivy security scan job (CRITICAL/HIGH severity) | MEDIUM | small | C2 |
| D2 | Configure Trivy SARIF upload to GitHub Security | MEDIUM | trivial | D1 |
| D3 | Document rollback procedure in ops documentation | MEDIUM | small | C4 |
| D4 | Verify non-root container user (uid 1000) in Dockerfile | LOW | trivial | None |

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
D3 → (after C4)
D4 → (already verified - already done in Dockerfile)
```

**Critical Path:** A1 → A2/A3 → B1 → C1 → C4 (sequential, ~12 days max calendar time with proper parallel execution)

---

## 5. Resource Constraints & Mitigation

### 5.1 GitHub Actions Free Tier Limit (2000 min/month)

| Mitigation | Implementation |
|------------|----------------|
| Path filters | Skip CI on docs-only changes (`paths-ignore`) |
| Job optimization | Cache uv dependencies, use efficient runners |
| Branch gating | Only run full pipeline on `main` (develop: CI only) |
| Duration budget | Estimated ~2,160 min with 10 runs/day; reduce to ~1,200 with optimizations |

### 5.2 VPS Constraints (4 CPU, 8 GB RAM)

| Consideration | Mitigation |
|---------------|------------|
| Single server | No multi-stage deployment needed |
| Docker ephemeral | Ensure proper volume persistence for backups/media |
| Resource spikes | Build containers locally, deploy pre-built images |

### 5.3 Pre-implemented Components

| Component | Status | Notes |
|-----------|--------|-------|
| Non-root user (uid 1000) | ✅ Already in Dockerfile | Line 86-87 in docker/Dockerfile |
| Coverage upload | ✅ Already configured | CI workflow line 86-91 |
| PostgreSQL 18 service | ✅ Already configured | CI workflow line 31-42 |
| Build cache (registry) | ✅ Partial | Currently uses registry cache; should migrate to GHA cache |

---

## 6. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| GitHub Actions time limit exceeded | MEDIUM | HIGH | Implement path filters; monitor usage; consider public repo for unlimited minutes |
| SSH key compromise | LOW | HIGH | Use ED25519 keys; rotate quarterly; restrict deploy user permissions |
| Trivy scan blocks deploy | LOW | MEDIUM | Run as non-blocking job; use `ignore-unfixed: true` |
| Database migration failure | MEDIUM | HIGH | Advisory lock prevents concurrent runs; test migrations in CI; backup before deploy |
| Rollback procedure failure | LOW | MEDIUM | Document; test with known-good SHA tag |
| Secret leak in logs | LOW | CRITICAL | Review workflow for proper secret masking; use `::add-mask::` for custom secrets |

---

## 7. Verification Steps

After implementation:

1. **CI Verification:**
   - Push to `develop` branch → verify CI runs (no build/deploy)
   - Push to `main` branch → verify all jobs execute in parallel
   - Open PR → verify CI runs with same behavior as push

2. **CD Verification:**
   - Run workflow dispatch with empty tag → latest `main` image deploys
   - Verify health check passes after deployment
   - Verify containers running: `docker compose ps` on VPS

3. **Rollback Verification:**
   - Trigger deploy with specific SHA tag
   - Verify old version is pulled and running

---

## 8. Files to Create/Modify

| Action | Path |
|--------|------|
| Rename & Modify | `.github/workflows/ci.yml` → `ci-cd.yml` (add workflow_dispatch, concurrency, CD jobs) |
| Update | Documentation (rollback procedure, deployment guide) |

### 8.1 Deployment Commands Reference

The deploy job will execute on VPS:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop
docker compose -f docker-compose.yml -f docker-compose.prod.yml rm -f  
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker image prune -f
```

---

## 9. Estimated Timeline

| Stage | Tasks | Calendar Time |
|-------|-------|-------------|
| A: Preparation | A1-A7 | 1 day |
| B: CI Enhancement | B1-B5 | 1 day |
| C: CD Extension | C1-C6 | 2-3 days |
| D: Security | D1-D4 | 1 day |
| **Total** | **21 tasks** | **5-7 days** (with testing/validation) |

---

## 10. Effort Summary by Type

| Effort | Tasks |
|--------|-------|
| trivial | A1, A2, A3, A7, B1, B4, B5, C5, C6, D2, D4 |
| small | A4, A5, A6, B2, B3, C1, C2, C3, D1, D3 |
| medium | C4 |

**Estimated effort:** 1 medium, 10 small, 10 trivial tasks.