SL PPC Daily Planner V1.9.22

Fix: A/B Forming synchronization no longer assumes every A/B member found across all process sections also has a Forming row. This was the direct cause of IndexError: single positional indexer is out-of-bounds at connected_rules_v170.py line 51.

The rebuild now uses only actual Forming members and checks for an empty match before iloc[0]. Existing V1.9.21 test-work and adaptive-pie rules are preserved.
