# Privacy policy

## Data minimization

Retain process meaning, not document bodies. Evidence may be a sanitized excerpt (at most 2000 characters), a content hash, or a permitted reference. Do not retain both when one is sufficient. Full transcripts, full contracts, full chat logs and full source files are never retained — oversized excerpts and summaries are rejected mechanically.

Automatic detection covers common credentials, bearer tokens, JWTs, OpenAI/GitHub/AWS-shaped keys, private keys, Chinese national identifiers, card-like numbers, email addresses and Chinese mobile numbers. Pattern detection is a safety net, not a guarantee. Business secrets and uncommon personal data require human review.

## Two lawful capture modes

**Enterprise-managed capture** runs under a harness-provided Enterprise Capture Authorization (see [enterprise-authorization.md](enterprise-authorization.md)). Employee invocation under a valid grant is the approved entry action; no per-record interactive confirmation is required. The runtime fails closed without it and never lets a payload authorize itself.

**Personal explicit capture** keeps the v1 gate: the preview exposes redaction categories and paths, inferred steps, adoption state, step count and retained evidence; the human confirms interactively; commit atomically consumes the exact-hash-bound confirmation once. Any edit requires a fresh `prepare`.

## What is never collected

Employee scores, AI usage scores, productivity ranks, or any people ranking — rejected mechanically at validation. Other conversations, other applications, devices, screens, or business systems — never read; there is no background or passive capture.

## Access and retention

File permissions, encryption at rest, retention time and deletion authority belong to the deploying enterprise; the grant's `retention_policy` reference is recorded with each enterprise record but enforced by the deployment. Business-context references and external identifiers are hashed before persistence. Before production use, the organization must define access control, backup encryption, retention and lawful deletion procedures.
