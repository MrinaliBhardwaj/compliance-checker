# Infrastructure — AWS ap-south-1 (Mumbai)

Data residency is non-negotiable for NBFC trust + DPDP posture (PRD §12). **Every**
stateful service is pinned to `ap-south-1`; no customer data leaves the region.

## Target topology (Phase 1)

| Concern | AWS service (ap-south-1) | Notes |
|---|---|---|
| App + worker | ECS Fargate (2 services: `api`, `worker`) | one image, two commands |
| Database | RDS for PostgreSQL 16, encryption at rest (KMS) | RLS enabled by migration `0002` |
| Cache + queue | ElastiCache for Redis | Arq job backbone |
| Object storage | S3 bucket, SSE-KMS, tenant-prefixed keys | evidence documents; signed URLs only |
| Vector DB | Qdrant on Fargate (EBS-backed) or managed in-region | RAG corpus + per-tenant doc namespace |
| Secrets | AWS Secrets Manager | JWT secret, `REGIS_FIELD_KEY`, Anthropic key |
| Email | SES (ap-south-1) | reminders, escalations, invites, digests |
| LLM | Claude via in-region endpoint / Bedrock (ap-south-1) | keep inference in-region |
| Frontend | Vercel (or CloudFront + S3) | static; talks to the API over HTTPS |

## Security baseline wired to infra (PRD §12)
- RLS tenant isolation (DB) + RBAC (app JWT).
- Encryption at rest (RDS KMS, S3 SSE-KMS) + TLS in transit.
- Field-level encryption for PAN/CIN/TAN (`REGIS_FIELD_KEY`, app layer) on top of at-rest.
- Append-only `audit_log` (DB trigger from migration `0002`).

## Modules to author (skeleton — not yet provisioned)
```
infra/terraform/
  main.tf            # provider "aws" { region = "ap-south-1" }, remote state (S3+DynamoDB lock)
  vpc.tf             # private subnets for RDS/Redis; NAT for Fargate egress
  rds.tf             # postgres 16, kms, parameter group (rls-friendly), backups
  redis.tf           # elasticache
  s3.tf              # evidence bucket, SSE-KMS, block public access, lifecycle
  ecs.tf             # cluster, api + worker task defs, ALB, autoscaling
  secrets.tf         # secrets manager entries -> task env
  ses.tf             # verified domain/identity for notifications
  qdrant.tf          # fargate service + EBS, in-region
```

> Phase 1 keeps this lean and single-region. No multi-region, no cross-account —
> deliberately out of scope until after the first 20 customers.
