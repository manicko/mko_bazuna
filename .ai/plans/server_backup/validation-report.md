# Validation Report: Server Backup Implementation Plan

## Review Findings Validation Results

### RF-1: Backup Integrity Verification
**Status:** ✅ ADDRESSED  
**Evidence:** Plan includes:
- `verify_db_dump()` function (lines 254-262) using `pg_restore --list`
- `restic check` after backup (line 319)
- Standalone `verify-backup.sh` script (lines 429-465)

### RF-2: Dynamic Volume Path Detection
**Status:** ✅ ADDRESSED  
**Evidence:** `get_media_volume_path()` function (lines 241-244) uses `docker volume inspect` to dynamically find media volume mountpoint.

### RF-3: Secret Management (Docker Secrets)
**Status:** ⚠️ PARTIALLY ADDRESSED  
**Evidence:**
- Docker secrets infrastructure defined in docker-compose.prod.yml (lines 145-147)
- Secrets configuration in docker-compose.yml (lines 192-196)
- Example secret template (lines 200-210)

**Issue:** backup.sh script (lines 236, 307, 312, etc.) references `${RESTIC_PASSWORD}` from environment instead of `/run/secrets/restic_pass`. The secrets infrastructure exists but is not integrated into the script.

### RF-4: Removed docker.sock Volume Mount
**Status:** ❌ NOT ADDRESSED - CRITICAL REGRESSION  
**Evidence:** Task 2.1 explicitly **adds** the docker.sock mount (line 144):
```yaml
- /var/run/docker.sock:/var/run/docker.sock:ro
```

This is a **security anti-pattern**. A container with docker.sock access can:
- Execute arbitrary commands on host
- Read any file on the host
- Create privileged containers
- Escape container isolation completely

The research.md explicitly notes backup must access volumes without exposing docker.sock.

### RF-5: Local Backups Cleanup After Sync
**Status:** ✅ ADDRESSED  
**Evidence:** `cleanup_local_backups()` function (lines 248-251) with 2-day retention, called after successful sync (line 330).

### RF-6: Task Numbering
**Status:** ✅ ADDRESSED  
**Evidence:** Task summary table (lines 580-597) shows consistent numbering (1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 5.1, 5.2, 6.1, 6.2, 6.3).

### RF-7: .env.docker.example Template
**Status:** ⚠️ PARTIALLY ADDRESSED  
**Evidence:** Task 1.2 specifies template content (lines 53-79). However, the file does not exist in the repository and must be created.

---

## Architectural Risks

| Risk | Severity | Description |
|------|----------|-------------|
| **docker.sock security** | 🔴 CRITICAL | Container can fully compromise host - violates security baseline |
| **Backup consistency** | 🔴 HIGH | No coordination with web/bot services - potential for inconsistent state |
| **Full media backup daily** | 🟠 MEDIUM | 50-200GB daily tar without differential - storage/bandwidth waste |
| **No backup service healthcheck** | 🟠 MEDIUM | Backup failures may go undetected |
| **Infinite loop container pattern** | 🟠 MEDIUM | Container should run idempotent backup, not loop forever |
| **Hardcoded volume names** | 🟠 MEDIUM | Media volume name `mko_bazuna_media_volume` hardcoded in multiple places |

---

## Scalability Concerns

| Concern | Impact | Recommendation |
|---------|--------|--------------|
| Media volume growth (50-200GB → 18TB/year) | High storage costs | Consider S3 migration for media (per research section 11.2) |
| No parallel backup support | Backup time increases | Split DB/media backup into separate services |
| Single-region B2 storage | No DR coverage | Add cross-region replication or secondary provider |

---

## Required Fixes

### 1. Remove docker.sock Mount (CRITICAL)
Replace Task 2.1's backup service configuration to eliminate the docker.sock mount. Alternative approaches:
- Use host path mount directly: `/var/lib/docker/volumes/mko_bazuna_media_volume/_data:/media_volume:ro`
- Use Docker volume mount syntax: `media_volume:/media_volume:ro` (read-only access)

### 2. Integrate Docker Secrets
Update backup.sh to read password from `/run/secrets/restic_pass` instead of environment variable:
```bash
# Instead of: RESTIC_PASS="${RESTIC_PASSWORD}"
RESTIC_PASS=$(cat /run/secrets/restic_pass)
```

### 3. Fix Backup Loop Pattern
Replace infinite loop with proper cron scheduling or use external scheduler.

---

## Implementation Conflicts

| File | Conflict | Resolution |
|------|----------|------------|
| docker-compose.prod.yml (existing) | Current backup service (lines 47-79) doesn't match plan | Plan replaces entirely - acceptable |
| .env.docker (existing) | Missing backup credentials | Add B2_KEY_ID, B2_APP_KEY, RESTIC_PASSWORD, HEALTHCHECK_UUID |
| .env.docker.example (missing) | Does not exist | Create from template in plan |
| docker/Dockerfile.backup (missing) | Does not exist | Create per task 2.2 |
| scripts/backup.sh (missing) | Does not exist | Create per task 3.1 |

---

## Rollout Analysis

**Execution Order Assessment:**
```
1. Configuration (parallel) - Safe
2. Docker Setup (sequential) - Safe, but docker.sock must be removed
3. Scripts (parallel after 3.1) - Safe
4. Makefile (after 3.x) - Safe
5. Documentation - Safe
6. Validation - Safe
```

**Rollback Feasibility:** Medium
- Backup service is profile-gated (`--profile backup`)
- Can disable profile and remove volumes
- Secrets volume cleanup required

---

## Recommendations

1. **IMMEDIATE:** Remove docker.sock mount before any deployment
2. **IMMEDIATE:** Update backup.sh to use Docker secrets
3. **SHORT-TERM:** Consider splitting media backup into separate cron job
4. **MEDIUM-TERM:** Evaluate S3-compatible storage for media files to eliminate volume backup complexity
5. **MEDIUM-TERM:** Add backup verification to CI pipeline (even if just smoke test)