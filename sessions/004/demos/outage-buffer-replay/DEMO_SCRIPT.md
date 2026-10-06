# Four-minute recording script

1. In Cloud, show the selected remote-site Edge job healthy.
2. Open <http://127.0.0.1:19480> and call out synthetic records, destination online, acknowledgements caught up, and queue zero.
3. Click **Run 12-second outage** once. The receiver actually returns 503; source admissions continue into the disk-backed queue.
4. Watch the destination restore and queue drain. Read the stable receiver-side sequence audit only after it reports verified.

Say “at-least-once with zero duplicates observed in this controlled run,” never “exactly once.”
