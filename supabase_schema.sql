-- ============================================================
-- FingerprintBridge — schema update
-- Only one change needed: add FingerprintSlot to the user table
-- ============================================================

alter table public."user"
add column if not exists "FingerprintSlot" integer unique;

-- That's it. Your existing tables are unchanged.
-- personnel_entry_logs and user are used as-is.

-- ── Optional: index for fast slot lookups on scan ─────────────
create index if not exists idx_user_fingerprint_slot
  on public."user" ("FingerprintSlot");

-- ── Optional: index for fast IN/OUT status lookups ────────────
create index if not exists idx_entry_logs_employee_id
  on public.personnel_entry_logs (employee_id, id desc);
