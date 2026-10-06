# Final browser acceptance

Captured from the integrated `main` branch on 2026-08-19.

- `signal-baseline-1440x900.png` and `signal-baseline-1920x1080.png` show routine compressor records crossing the network unchanged.
- `signal-verified-1440x900.png` and `signal-verified-1920x1080.png` show the receiver-derived filtered window and the exact protected incident acknowledgement.

The recorded windows observed 92.6% to 95.1% fewer acknowledged bytes after the filter revision. The pinned receiver payload and acknowledgement both carry the same event ID and exact `COMPRESSOR_OVERHEAT` code. A fresh browser load rehydrated that protected proof from the runtime snapshot rather than falling back to a routine record.

Both viewports loaded the bundled IBM Plex fonts, had no horizontal overflow, and produced no browser console errors. These captures are local Bento rehearsals, not evidence of an Expanso Cloud deployment. Cloud deployment remains a separate visible recording step.
