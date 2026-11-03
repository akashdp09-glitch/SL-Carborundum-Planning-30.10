SL PPC DAILY PLANNER V1.7.4 — CONTROLLED RUNTIME FIX

Root cause fixed:
build_daily() used active_post_machines and used_post_people in the post-firing Grinding/Cutting scheduler,
but these two per-day resource trackers were initialized only in another scheduler path, not in build_daily().

Controlled fix:
- Initialize active_post_machines={} in build_daily().
- Initialize used_post_people={} in build_daily().
- No capacity values, lead-time rules, Plan 2026 mapping, firing anchors, routing rules, or scheduling priorities were changed.

Purpose:
Preserve V1.7.3 CAPACITY + LEAD TIME CONTROLLED logic while removing the NameError.
