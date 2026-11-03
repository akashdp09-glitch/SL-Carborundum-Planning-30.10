SL PPC FIRING PLANNER V1.9.14

1. Strict Forming Close default = OFF.
   Physical verified formed/ready quantity can be planned even when the full WO is not formally closed.
2. Existing exact physical/furniture pattern remains the release authority.
3. If an R/large-part exact pattern cannot be validated, the app now offers an A4 R/Large-Part Furniture Review Excel + PDF.
   This review shows kiln, program, WO, qty, part footprint/height, chamber dimensional fit and the exact physical/furniture error.
   It is clearly marked NOT RELEASED and does not bypass furniture validation.
4. Existing V1.9.13 math/import, solid kiln stack, PL Mgr Validation and Operator Print fixes retained.

Validation:
- All Python sources compile successfully.
- Strict default OFF static check passed.
- R large-part review Excel + PDF generation runtime-tested.
