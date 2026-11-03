SL CARBORUNDUM SMART FACTORY CENTER V16

FAST PART TRACKING
- Desktop Home: type Work Order and see Plan-2026 location/status, quantity and dates.
- Mobile: one large Work Order box + SHOW STATUS + CAMERA QR.
- WO search ignores case and punctuation: P005-110826, p005110826 and P005110826 resolve to the same key.
- Mobile shows PLAN-2026 status separately from LAST PHYSICAL AUDIT.

PLAN-2026 MAPPING (user-confirmed)
- C / กำหนดเข้าคลัง = initial due / scheduled warehouse receipt date.
- E / กำหนดส่งใหม่ = revised delivery date (kept separately).
- IB / กำหนดส่งมอบขาย = scheduled sales delivery date (kept separately).
- BY / จำนวนโม่ = number of mill batches.
- HH:HX milestone fields are used to derive the latest Plan-2026 process/location/status.
- The supplied Row_3_Thai_English_Cell_Mapping.xlsx is included as a reference. A revised mapping can be uploaded once in Upload / Replace Source Files and is saved centrally.

MIXING CAPACITY
The current CAP ผสม sheet contains BOTH CAP-โม่/วัน (mills/day) and CAP-เครื่อง(kg)/วัน (kg/day).
V16 therefore shows planned BY mill batches, mills/day capacity, and kg/day nominal capacity separately. It does not assume an arbitrary kg per mill.

PRODUCTION WIP
Tree: Planning Department -> Production WIP Comparison.
Upload location: Upload / Replace Source Files -> Production WIP files.
There is only one upload location; the comparison page reads the central copies.

CAMERA NOTE
Live browser camera scanning depends on phone/browser camera permission and secure-context rules. V16 first tries live rear-camera QR using the browser BarcodeDetector. If the browser blocks live camera on LAN HTTP, it falls back to the phone camera/file capture. Existing QR URLs can also be scanned directly by the phone's normal camera.

SOURCE FILE RULE
Original uploaded files are never edited. Revised mapping/audit/planning outputs are software-owned copies.
