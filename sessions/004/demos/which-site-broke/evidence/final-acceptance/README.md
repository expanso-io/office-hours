# Final browser acceptance

Captured from the integrated `main` branch on 2026-08-19.

- `lineage-baseline-1440x900.png` and `lineage-baseline-1920x1080.png` show ten anonymous source slots, a receiver-observed `SENSOR_TIMEOUT`, and `SOURCE UNKNOWN`.
- `lineage-verified-1440x900.png` and `lineage-verified-1920x1080.png` show receiver-derived attribution to `wind-west / turbine-07`, app `1.8.3`, pipeline `lineage-v2`.

In both states, the pinned payload event ID exactly matched the pinned HTTP 200 acknowledgement. The acknowledgement remains available after the event leaves the rolling activity window. Selecting `turbine-08` changed the inspection view and URL but did not change the receiver-derived `turbine-07` attribution.

Both viewports loaded the bundled IBM Plex fonts, had no horizontal overflow, and produced no browser console warnings or errors. This was a local rehearsal; Expanso Cloud deployment remains a visible manual recording step and was not executed in this acceptance run.
