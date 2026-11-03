V1.6.1 STOCK + DASHBOARD CONTROL
- Stock parser intentionally reads ONLY 3 user-confirmed sheets.
- Abrasive: BalanceStock = Excel column N. Also reads code, material name, order on hand/open production, physical stock, waiting to receive, under LAB test, movement and remarks.
- ทรายบด-ล้างR: BalanceStock = Excel column E. Reads code, material/type, Orderonhand, physical stock and supporting fields.
- ทรายบด-ล้างSPB: BalanceStock = Excel column E. Same controlled mapping.
- No fallback to other stock sheets. Missing controlled sheet/column raises an explicit error instead of false zero stock.
- Stock analysis is English, includes shortage/urgency reminder and charts.
- TV dashboard TODAY/TOMORROW section uses a bordered, alternating-row table for clearer large-screen viewing.
- Existing lead-time, WIP, Daily Plan, MPS/MRP and firing logic retained.
