# Final browser acceptance

Captured from the integrated `main` branch on 2026-08-19.

- `outage-1440x900.png` and `outage-1920x1080.png` show the healthy pre-run state.
- `outage-verified-1440x900.png` and `outage-verified-1920x1080.png` show the bounded receiver audit after the browser-triggered outage.

The verified run audited 67 Edge-admitted sequences through the frozen high-water mark: 67 acknowledged, 0 missing, and 0 duplicates observed. The UI deliberately labels the transport as at-least-once and reports Edge drop telemetry as not measured.

Both viewports loaded the bundled IBM Plex fonts, had no horizontal overflow, and produced no browser console errors. These captures are local Bento rehearsals, not evidence of an Expanso Cloud deployment. Cloud deployment remains a separate visible recording step.
