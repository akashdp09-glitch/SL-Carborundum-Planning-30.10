# RC29.38 — Major delivery-risk customer names

- Fixed HTML dashboard risk-order rows showing N/A when a valid customer name exists in Plan-2026.
- Risk rows now refill blank or placeholder customer values from Plan-2026 by normalized work order.
- Thai and English display continue to use the source customer name and existing bilingual display helper.
- Preserved valid customer names already present in risk data.
- Validation: Python syntax compilation passed. Full HTML rendering could not be run in this build environment because Plotly is unavailable.
- This package is based on the locally available RC29.37 source plus this focused fix.
