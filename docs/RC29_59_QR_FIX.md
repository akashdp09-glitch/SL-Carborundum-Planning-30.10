# RC29.59 — QR image backend repair

Fixes ModuleNotFoundError: qrcode.image.pil on Home and other QR creation routes. The qrcode core builds the QR matrix; a shared PNG encoder writes the image without the optional qrcode/Pillow image backend. Desktop connection QRs, tracking portal, work-order labels, mobile and unidentified-part QR creation share this encoder. The startup readiness probe now generates a real QR PNG using the current code folder instead of merely importing qrcode.

The previous installation's runtime is intentionally shared by the existing Windows launcher; that path alone is not an error. This repair does not change the chosen shared runtime, factory data folders, existing passwords or firing rules. No package installation is needed specifically for the missing qrcode.image.pil backend after applying this code fix. Core dependencies are still required.

Small repair ZIP: close the program, extract its contents into your existing RC29.58 folder containing hub.py, choose Replace for these program files, then run the existing START_SL_CARBORUNDUM_PLANNING_CENTER.bat. Do not replace or delete CENTRAL_DATA. Alternatively use the complete RC29.59 code ZIP in its new version folder and reuse the existing central data.

Validation: QR images decode through OpenCV while imports of qrcode.image.pil and PIL are deliberately blocked. File/BytesIO outputs agree. Exact physical scanner and Windows startup remain on-device checks. Prior firing review limitations remain unchanged.

Results: 29 focused QR/planning checks passed; mobile 98 passed, 1 skipped. Runtime/QR decision checks: 19 passed, 2 inherited tests still expect the retired .venv path rather than the existing RUNTIME/venv policy. Those two failures are reported unchanged; this fix deliberately preserves shared-runtime selection.
