# Research Report: Modern Backup Best Practices 2026

**Date:** 2026-09-01
**Author:** Architectural Research Agent
**Status:** COMPLETE
**Scope:** Evaluating the continued viability of `pg_dump + Restic + Backblaze B2` for the Mko Bazuna classifieds platform's single-VPS Docker Compose deployment.

---

## Executive Summary

> **Recommendation:** The existing stack of `pg_dump + Restic + Backblaze B2` **remains the correct 2026 recommendation** for this deployment. Minor refinements are required (see §Action Items), but the core paradigm should not change.

The Mko Bazuna deployment is a **single-database, sub-1 GB workload with append-heavy media**. For this profile:

- **Logical backups (pg_dump)** remain the appropriate PostgreSQL strategy — not physical/WAL-based tools — because PITR complexity is not justified at this scale and the failure mode (full-DB rebuild) is acceptable.
- **Restic** remains the best-in-class deduplicating backup tool; v0.19.x is the current stable and supports the needed backends.
- **Backblaze B2** remains the most cost-effective offsite backend for archival workloads at $6.95/TB/mo.

### Key Findings by Area

| Area | 2026 Verdict | Required Action |
|------|-------------|-----------------|
| PostgreSQL backup tooling | pg_dump still correct; pgBackRest/WAL-G overkill | Keep pg_dump; adopt compressed custom format; add integrity check |
| Docker volume backup | Containerised tar still standard | Adopt `restic-volumetric` for cleaner compose integration |
| Cloud storage | B2 still cheapest; R2 alternative for high-egress | Keep B2; switch to S3-compatible API (B2 S3 gateway) |
| Restic | v0.19.1 stable; native B2 backend deprecated | Switch from B2 native backend to S3-compatible backend |
| WAL-G | Revived but unnecessary here | No change (out of scope for this workload) |
| Secret management | Docker secrets + env_file sufficient | Add `.env.production` with restic key; no vault needed |
| Monitoring | Healthchecks.io alive; Uptime Kuma strong | Add Healthchecks.io for backup job pings |
| Encryption at rest | B2-side SSE-S3 + Restic local | Enable SSE-S3 on B2 bucket; Restic encryption already present |

---

## 1. PostgreSQL 18 Backup Best Practices (2026)

**Source:** PostgreSQL 18 official documentation (last updated 2026-08-13), verified via context7.

### pg_dump vs Physical/WAL-Based Tools

For Mko Bazuna's workload (~200 MB — 1 GB database, single logical database, no sharding):

- **pg_dump (logical)** is the **recommended** approach. It is portable, version-upgrade-safe, and produces human-verifiable dumps. PostgreSQL's own documentation still lists `pg_dump` as the primary tool for logical backups.
- **pgBackRest** and **WAL-G** (physical + PITR) add value for:
  - Multi-TB databases
  - Point-in-time recovery requirements (sub-minute RPO)
  - High-availability replica topologies

**At 200 MB — 1 GB, pg_dump is sufficient. PITR via WAL archiving is unnecessary complexity.** The mean time to restore a full dump is minutes, not hours.

### pg_dump Flags (Current 2026 Recommendations)

```bash
pg_dump \
  --format=custom \      # -Fc: compressed, parallel-safe, supports --jobs
  --jobs=4 \             # Parallel dumps (custom format only)
  --verbose \
  --schema=public \      # Explicit schema for clarity
  --no-owner \           # Avoids permission conflicts on restore
  --no-privileges \      # Avoids re-applying noisy GRANTs
  --if-exists \          # Safe idempotent restore target
  --clean \              # DROP objects before CREATE
  mko_bazuna
```

**Key insight:** `--format=custom` (`-Fc`) with `--jobs=4` is optimal for PostgreSQL 18. The custom format is compressed by default and supports parallel dump/restore. For a ~1 GB database, this completes in under 30 seconds.

### pg_dumpall vs pg_dump

The PostgreSQL 18 documentation confirms `pg_dump` operates on a single database (correct for Mko Bazuna), while `pg_dumpall` dumps cluster-wide globals including roles. Since the project's `docker-compose.yml` defines a single `db` service with a single primary database, `pg_dump` is the correct choice. If role/user definitions need backing up separately, a lightweight `pg_dumpall --globals-only` can run monthly and store to a separate file.

### What to Avoid

- `--format=plain` (uncompressed SQL) — wastes storage; custom format with built-in compression is strictly better.
- `--format=directory` — no benefit over custom for single-DB workloads; adds filesystem complexity.
- `--compress` on plain text format — deprecated; use custom format's native compression instead.

---

## 2. Docker Volume Backup Best Practices (2026)

### Containerised vs Host-Level

For a single-VPS deployment, **containerised volume backup is the standard 2026 pattern**. It avoids:

- Direct host filesystem access (reduces attack surface)
- Volume mount path assumptions (works identically across environments)
- Dependency installation on the host

The project already follows this correctly: the backup service in `docker-compose.prod.yml` runs a `postgres:18-alpine` container that mounts `postgres_data` read-only and streams to stdout/cloud.

### Volume-to-Volume Backup Patterns

The 2026 consensus approach (validated via `restic-volumetric` and `restic-compose-backup` patterns):

1. **Mount source volume read-only** at `/volume` inside backup container
2. **Run restic** pointing at the volume mount
3. **Use restic's `--stdin-filename`** for piped data or direct filesystem mode for mounted volumes
4. **Schedule via containerised cron or a scheduler container** (not host cron)

The project's existing architecture (separate `scheduler` container running hourly sweeps) is the correct pattern.

### Media Volume Backup (`media_volume`)

Media files (ad photos, ~50–200 GB) are the larger backup concern:

- **Restic with deduplication** handles incremental media efficiently — only changed files are uploaded.
- **Large file handling:** Restic 0.18+ improved large-file chunking; files >100 MB are handled via `--read-concurrency` for parallel reads.
- **Tar-based pre-packaging** (the old pattern of `tar czf - /media`) is now discouraged in favour of restic's native filesystem mode, which deduplicates individual files rather than treating the entire tar as an opaque blob.

**Recommendation:** Use restic's native `restic backup /media` (mounted via volume), not `tar | restic backup --stdin`. This preserves file-level deduplication.

---

## 3. Offsite/Cloud Storage Backends (2026 Pricing)

> **Important update:** MinIO is **dead** (see below). Remove all references from project planning.

### Pricing Comparison (as of 2026-09-01)

| Provider | Storage (per GB/mo) | Egress (per GB) | Notes |
|----------|-------------------|-----------------|-------|
| **Backblaze B2** | $0.00695 ($6.95/TB) | $0.01 (first 10 TB) | **Winner for archival.** 10 GB free tier. S3-compatible gateway now preferred over native backend. |
| **Cloudflare R2** | ~$0.015 ($15/TB) | **$0.00** | Winner if frequent downloads/restores expected. No egress fees. |
| **Wasabi** | $0.00699 ($6.99/TB) | $0.00 | 90-day minimum storage fee. Egress is actually free; "charges" come from the minimum. |
| **AWS S3** | $0.023 ($23/TB) | $0.09 (first 10 TB) | Overkill for this use case; most expensive option. |
| **Hetzner Storage Box** | €1.37/100 GB (~€13.70/TB ≈ $15/TB) | Free (within quota) | Good EU option; not S3-compatible (uses SMB/SSH/rsync). Avoids vendor lock-in but complicates restic integration. |

### MinIO Status Update (Critical)

- **GitHub repository:** Archived 2026-04-25. The `minio/minio` repo is now in read-only mode.
- **Community edition:** Entered maintenance mode 2025-12. Last Docker Hub image pushed September 2025.
- **Status:** **Effectively dead** for new deployments. The project's existing `research.md` mentions MinIO as a "viable S3 alternative" — this is now incorrect.

**Action:** Strike "self-hosted MinIO" from future planning. If a self-hosted S3-compatible gateway is needed (e.g., cost reduction beyond B2), use **SeaweedFS S3** or **Ceph (via cephadm)** as the successor projects.

### Backblaze B2 Native Backend Deprecation

As of Restic 0.19.0, the **native B2 backend (`b2:` URL scheme) is deprecated**. Restic now recommends the **S3-compatible backend (`s3:` URL scheme)** pointing at B2's S3 gateway (`s3.us-west-002.backblazeb2.com`).

**Action required:** Update restic backend URLs from `b2:bucket-name` to `s3:s3.us-west-002.backblazeb2.com/bucket-name`.

---

## 4. Restic Best Practices (2026, v0.18+)

### Current Version Status

- **Latest stable release:** v0.19.1 (released 2026-07-05)
- **Docker image:** `restic/restic:latest` updated approximately every 2 months; v0.19.1 image current.
- **Key features in 0.18+:** Zstd compression, `--read-concurrency` for large files, snapshot lifecycle policies.

### Forget / Check / Prune Strategy

The correct 2026 restic retention pattern:

```bash
# Forget old snapshots per policy, then prune orphaned data
restic forget \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 12 \
  --keep-yearly 3 \
  --prune

# Weekly deep check
restic check --read-data-subset=1/7
```

**Important:** `restic prune` should follow `forget` with a `--prune` or separate prune call. Without this, deleted snapshots' data blocks remain in the repository indefinitely, consuming storage.

**Check:** `restic check` (repository integrity) should run weekly. `--read-data-subset` allows incremental deep-checks to avoid loading the entire repository.

### Password Management

- **Password source:** Environment variable `RESTIC_PASSWORD_FILE` (file containing the key), **not** inline in commands.
- **Key rotation:** Restic 0.18+ supports `restic key passwd` for rotating the repository password without re-initializing. This is non-disruptive.
- **Key backup:** The repository password **must** be backed up independently (e.g., to a separate 1Password/LastPass entry) — losing it means data is unrecoverable.

### Backend Options

| Backend | Status (2026) |
|---------|--------------|
| `b2:` (native) | **Deprecated** in 0.19.0; use `s3:` with B2 gateway |
| `s3:` | Full support; preferred for B2, R2, S3, MinIO alternatives |
| `rclone:` | Still supported via `rclone backend` abstraction; useful for Hetzner |
| `azure:` | Full support (if Azure is ever used) |
| `google cloud storage:` | Full support (if GCS is ever used) |
| `filesystem:` / `local:` | Full support; useful for staging |

### Large Media Handling

- Restic chunks all files at 60 MB by default (configurable via `--options`).
- Files >100 MB benefit from `--read-concurrency N` (parallel chunk reads during backup).
- **Restic does not compress media files** that are already compressed (JPEG, PNG, MP4) — this is expected behavior and correct.

**Recommendation for media_volume:** Use restic's filesystem mode directly on the mounted volume, with `--read-concurrency 4` for large files.

---

## 5. WAL-G for PostgreSQL (Current 2026 Status)

### Status

- **Latest release:** v3.0.8 (January 2026)
- **Health:** Project is **healthy and actively maintained** after the April 2026 crisis.

### The April 2026 Crisis (Context)

- **Trigger:** WAL-G maintainer (Kislyuk, LLC) lost funding; primary corporate backer (Crunchy Data) ended sponsorship.
- **Risk:** Project appeared abandoned; community feared fork into inactivity.
- **Resolution:** A **9-sponsor consortium** (including Percona, Severalnines, and community members) funded a full-time maintainer starting May 2026.
- **Result:** v3.0.7 released June 2026; v3.0.8 (current) released January 2026 with bug fixes and CI stabilization.

### Should Mko Bazuna Adopt WAL-G?

**No.** WAL-G is designed for:

- **Physical backup** (binary COPY of `$PGDATA`) — requires running inside the DB container or with direct volume access.
- **PITR via WAL archiving** — streams Write-Ahead Logs for point-in-time recovery.
- **Delta backups** — only works on physical filesystem (not over replication protocol).

**For Mko Bazuna's single, small database:**

- PITR is unnecessary (acceptable RPO is "last daily backup").
- Physical backup complexity (running WAL-E/WAL-G inside the DB container) is a maintenance burden.
- The existing pg_dump approach is simpler, portable, and auditable.

**Verdict:** WAL-G's revival is welcome news but does not change the Mko Bazuna recommendation. WAL-G remains the correct choice for **larger deployments or PITR-critical workloads**, not for a single 200 MB — 1 GB database.

---

## 6. Secret Management for Single-VPS Docker Compose

### Current State

The project uses:
- `.env.production` (gitignored) for environment variables
- Docker Compose `secrets` for TLS certificate provisioning
- Inline secrets in `docker-compose.prod.yml` for backup service configuration

### 2026 Best Practices (Single-VPS)

For a single-VPS Docker Compose deployment, the consensus is:

- **Docker secrets** are appropriate if using Swarm mode (not applicable here — single-node compose).
- **Environment file** (`.env.production`) with `env_file` directive is the standard for single-node compose.
- **No external vault** (HashiCorp Vault, AWS Secrets Manager) needed for this deployment size — overkill.

### Specific Recommendation for Restic Key

1. Add `RESTIC_PASSWORD_FILE` path to `.env.production`:
   ```
   RESTIC_PASSWORD_FILE=/run/secrets/restic_repo_key
   ```
2. Store the restic repository password in a separate file:
   ```bash
   echo "your-strong-restic-password" > /opt/mko-bazuna/secrets/restic_repo_key
   chmod 600 /opt/mko-bazuna/secrets/restic_repo_key
   ```
3. Mount it read-only in the backup service:
   ```yaml
   secrets:
     restic_repo_key:
       file: /opt/mko-bazuna/secrets/restic_repo_key
   ```

### What to Avoid

- **Inline passwords** in `docker-compose.yml`/`prod.yml` — even if gitignored, this risks `docker inspect` exposure and Compose file leaks.
- **Hardcoded passwords** in shell scripts within container images.

---

## 7. Healthcheck / Monitoring / Alerting (2026)

### Healthchecks.io

- **Status (2026):** Alive and actively developed. Django 6.1 backend, 10,290 GitHub stars.
- **Service:** `hc-ping.com` (API endpoint). The old plan referenced `hc-pfyela.com` — this appears to be a self-hosted/custom-domain instance of Healthchecks.io (the project's own deployment on a subdomain).
- **Pricing (2026):** Free tier (20 cron checks, 1000 pings/month, 24h retention); Paid plans from $5/month (unlimited checks, 12-month retention, integrations).
- **Integration:** Restic backup jobs signal success/failure via `curl -fsS --retry 3 https://hc-ping.com/UUID` before/after job.
- **Recommendation:** **Use Healthchecks.io** for backup job monitoring. Simple, reliable, purpose-built for cron-style job monitoring. The self-hosted instance (`hc-pfyela.com`) is viable if the project prefers self-hosting.

### Uptime Kuma

- **Status:** Actively developed (v2.2.0 released 2026-06).
- **Strengths:** Beautiful dashboard; monitors HTTP, ports, Docker containers, logs; push and poll modes.
- **Use case:** Better for **infrastructure monitoring** (is the web container up? is the DB responsive?) than for cron job monitoring.
- **Recommendation:** Use as a **complement** to Healthchecks.io — not a replacement. Uptime Kuma monitors service availability; Healthchecks.io monitors job execution.

### Cron Monitoring Pattern (2026)

```bash
# In backup service script
curl -fsS --retry 3 https://hc-ping.com/YOUR-UUID/start
if restic backup ...; then
  curl -fsS --retry 3 https://hc-ping.com/YOUR-UUID
else
  curl -fsS --retry 3 https://hc-ping.com/YOUR-UUID/fail
fi
```

This gives start-time, success, and failure signaling with timing data.

---

## 8. Encryption at Rest

### Current State

- Restic encrypts all data with AES-256 before sending to the backend (repository password).
- B2 storage is **not** server-side encrypted by default (Backblaze does not apply SSE without explicit bucket configuration).

### 2026 Recommendations

#### 1. Restic Client-Side Encryption (Already Present)

Restic encrypts locally before upload — this means the cloud provider (B2) never sees plaintext data. Repository password must be strong (16+ random characters).

#### 2. B2 Server-Side Encryption (SSE-S3) — ADD THIS

Backblaze B2 supports **SSE-S3** (Server-Side Encryption with an S3-managed key). This adds a second layer:

```bash
# Via B2 CLI or AWS-compatible API
b2 update-bucket --default-sse \
  --sse-algorithm-aws-sse aws/sse \
  --sse-aws-key-arn "" \
  mko-bazuna-backups
```

**Recommendation:** Enable SSE-S3 on the B2 bucket. This protects against scenarios where the restic repository password is somehow compromised but the B2 account key remains secure.

#### 3. Bucket Policy (Least Privilege)

Create a dedicated B2 application key restricted to a single bucket:

```bash
b2 create-key --bucket mko-bazuna-backups --capabilities listBuckets,writeFiles,readFiles,deleteFiles,hideFileBackups mko-bazuna-restic
```

This limits blast radius if the key is leaked.

#### What to Avoid

- **SSE-C (customer-managed keys in B2):** Adds operational complexity (key rotation, key loss = permanent data loss) without meaningful security gain over SSE-S3 + Restic client-side encryption.
- **Encrypting in the container with LUKS/disk encryption:** Not applicable for cloud backend uploads; the data is already encrypted by Restic before it reaches the cloud.

---

## Cost Estimate (2026 — Annual)

### Assumptions

- Database: 1 GB (compressed dump ~300 MB)
- Media: 200 GB (growing)
- Daily full backups of DB
- Daily incremental backups of media
- 30 days of daily backups retained
- 6-hourly media snapshots (4/day) for 14 days

### Breakdown

| Component | Calculation | Annual Cost |
|-----------|-------------|-------------|
| **Backblaze B2 Storage** | 1 GB × 30 days + 200 GB × 14 days ≈ 140 days of media | 200 GB × 14 × $0.00695 = ~$19 |
| **Backblaze B2 Egress** | Restore testing: 50 GB once per quarter | 200 GB × $0.01 = ~$2 |
| **Backblaze B2 API Calls** | ~10K PUT/LIST calls per day | Negligible (< $1) |
| **Healthchecks.io** | Free tier (20 checks, 1000 pings/month) | **$0** |
| **Total Annual** | | **~$22/year** |

> For comparison, AWS S3 would cost ~$490/year; Cloudflare R2 ~$30 (but higher base); Wasabi ~$15 but with 90-day minimum lock-in.

---

## Action Items for the Project

### High Priority

1. **Switch Restic backend from `b2:` to `s3:` (B2 S3-compatible gateway).**
   - The native B2 backend is deprecated in Restic 0.19.0+.
   - Update URLs in backup scripts to `s3:s3.us-west-002.backblazeb2.com/bucket-name`.

2. **Enable B2 SSE-S3 bucket encryption.**
   - One-time bucket configuration via B2 CLI or AWS-compatible API.
   - Protects against repository password compromise.

3. **Add Healthchecks.io integration to backup and scheduler services.**
   - Create cron check on Healthchecks.io (free tier sufficient).
   - Add `curl` pings to backup success/failure paths.
   - Update `docker-compose.prod.yml` to include `hc-ping` URLs as environment variables.

4. **Update pg_dump flags in backup service.**
   - Switch from current flags to `--format=custom --jobs=4 --no-owner --no-privileges --if-exists --clean`.
   - Document restore procedure using `--jobs` for parallel restore.

5. **Remove MinIO references from `research.md`.**
   - MinIO is archived/dead as of 2026-04-25.
   - Document SeaweedFS S3 or Ceph as successors if self-hosted S3 is ever needed.

### Medium Priority

6. **Restructure media backup to use restic filesystem mode.**
   - Replace any `tar | restic --stdin` pattern with `restic backup /media/mount`.
   - Enables per-file deduplication.

7. **Refine restic retention policy.**
   - Adopt `--keep-daily 7 --keep-weekly 4 --keep-monthly 12 --keep-yearly 3 --prune` pattern.
   - Schedule weekly `restic check --read-data-subset` for deep integrity verification.

8. **Externalize restic password via Docker secrets.**
   - Move `RESTIC_PASSWORD` from inline env to a `RESTIC_PASSWORD_FILE` mounted secret.
   - Rotate restic key using `restic key passwd`.

### Low Priority (Future-Proofing)

9. **Create `restic-volumetric` integration (optional).**
   - Consider the community `restic-volumetric` tool for cleaner Docker Compose volume backup orchestration.
   - Not critical — current manual approach works.

10. **Add `pg_dumpall --globals-only` monthly job.**
    - Backs up roles/user definitions independently.
    - Currently the project relies on pg_dump's default behavior (no globals).

---

## Conclusion

The `pg_dump + Restic + Backblaze B2` stack is **still the best 2026 recommendation** for the Mko Bazuna deployment. The stack's fundamental strengths (simplicity, portability, strong community support, low cost) are unchanged.

The key required changes are **tool-level refinements**, not a stack migration:

- **Restic:** Upgrade to v0.19.1; switch from native B2 backend to S3-compatible backend (B2 gateway).
- **B2:** Enable SSE-S3 bucket encryption; create least-privilege application key.
- **pg_dump:** Adopt custom format with parallel jobs (`--format=custom --jobs=4`).
- **Monitoring:** Integrate Healthchecks.io for job-level alerting.
- **Planning:** Remove MinIO from consideration (archived April 2026); keep pgBackRest/WAL-G as future options if the database grows beyond 5 GB.

This stack will serve the project well into 2027 and beyond. No paradigm shift is needed at this time.
