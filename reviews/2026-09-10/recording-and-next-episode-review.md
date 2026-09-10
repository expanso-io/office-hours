# Office Hours: recording check and next-episode review

Review date: September 10, 2026. Scope: verify the recording, review the first edited replay and the second live archive, and propose episode three. No edited export, OBS setting change, or Cloud run was made during this review.

## Recording verdict

**The full September 10 stream was not recorded locally by OBS. Its Twitch archive is available and has been downloaded.**

| Evidence | Result |
|---|---|
| Local OBS file | `/Users/daaronch/Movies/2026-09-10 08-59-35.mkv` |
| Actual media | H.264, 3840 × 2160, 60 fps; AAC stereo, 48 kHz |
| Duration | 12.65 seconds; complete decode check passed |
| Recording lifecycle | 08:59:35.753–08:59:48.791 PDT |
| Streaming lifecycle | 08:59:50.662–09:29:16.566 PDT |
| Full local recording during or after this stream | None in this OBS session; OBS shut down at 09:29:21 |
| Recovered archive | [Twitch replay](https://www.twitch.tv/videos/2870456117), 29:23.516, H.264 1920 × 1080 at 60 fps |
| Rendering lag during stream | 9,060 frames, 8.5% |
| Network drops during stream | 147 frames, 0.1% |

The 4K recording configuration worked for the short test. It did not start recording automatically with the stream. I configured separate recording and streaming outputs earlier but did not enable **Automatically record when streaming**. Configuration verification was not proof that a full recording would be made.

The Twitch copy is a recovery source at 1080p. Re-encoding it at 4K will not recover native 4K detail. The log points to substantial rendering stalls, but does not establish which application or resource caused them.

### Reviewed sources

- Episode one: [YouTube edited replay](https://www.youtube.com/watch?v=Utvn1Mddyfo), 46:34.494, downloaded at 1920 × 1080 / 30 fps. This is the edited version, not the original live master. Local frame and transcript review was used after Gemini preprocessing failed.
- Episode two: [September 10 Twitch archive](https://www.twitch.tv/videos/2870456117), 29:23.516, downloaded at 1920 × 1080 / 60 fps. The channel still labels it “Office Hours #0”; this report calls it episode two to match the repository's sequence.
- The first source is already edited and the second is a live archive. Differences in pacing should not be treated as a controlled comparison of presenter improvement.

### Audio measurements

These are FFmpeg measurements of the downloaded files, not platform analytics or subjective listening scores.

| Source | Integrated loudness | True peak | Loudness range |
|---|---:|---:|---:|
| Episode one | −23.99 LUFS | −9.08 dBTP | 8.8 LU |
| Episode two | −23.04 LUFS | −5.34 dBTP | 14.6 LU |

Both files have headroom and are quiet overall. Level-match speech and control large changes in voice level before final loudness normalization. A practical editorial starting target is about −16 LUFS with a −1.5 dBTP ceiling, then listen on headphones and a phone speaker; this is a production choice, not a YouTube acceptance requirement. Do not simply add 8 dB throughout episode two: its peaks need limiting and quiet sections may contain room noise.

## Video review

The strongest material is the moment a change produces a visible result. Episode one has a particularly useful live field-change demonstration; episode two has concrete binary and multiline examples, but spends too much of its shorter runtime finding output and repairing the environment. Preserve the conversational delivery and audience predictions. Reduce the number of unrelated lessons.

These are editorial review windows, not a frame-accurate EDL. Timecodes use each downloaded source timeline. Check speech and transition boundaries in an editor. Suggested targets: episode one 18–24 minutes plus optional extras; episode two 12–16 minutes plus a separate benchmark extra. Neither target is an exported or timed cut.

### Episode 1: prioritized edit map

| Source window | Decision | Editorial direction |
|---|---|---|
| 00:00–03:44 | COMPRESS | Replace the broad opening with a 20-second problem and result preview. |
| 03:44–06:48 | KEEP / TIGHTEN | Establish Cloud, the edge node, synthetic source and tail pipeline; remove repeated navigation. |
| 06:48–08:47 | KEEP / TIGHTEN | Explain parsing and the keep/drop rule; trim the chat interruption. |
| 08:47–12:18 | KEEP | Deployment, live output and the hello.twitch field change are the clearest causal demonstration. |
| 12:18–17:35 | COMPRESS | Sample-panel and predicate confusion: preserve one prediction, the actual result and the correction. |
| 17:35–18:37 | KEEP | Useful honesty: fewer messages can still mean more bytes after enrichment. |
| 18:37–23:05 | KEEP / TIGHTEN | Parquet branch: shorten assistant waiting; file existence alone does not verify its contents. |
| 23:05–26:40 | BONUS / LABEL | Kafka configuration discussion is not a demonstrated delivery; clearly label the unexecuted example. |
| 26:40–33:18 | REPAIR | Schema and dead-letter discussion has ambiguous outcome and an invalid Kafka endpoint. Add a pickup that states what was and was not verified. |
| 33:18–40:37 | REVIEW / COMPRESS | Compress deployment-threshold troubleshooting; retain the file listing around 36:12 with its limits. Around 36:45–38:45, label the MD5 example a hash transformation, not secure anonymization: predictable sensor names can be guessed. Move the binary discussion to the bonus. |
| 40:37–44:45 | BONUS | Subprocess and batching are separate lessons. Configuration and illustrative averaging should not imply a completed production workflow. |
| 44:45–46:34 | TRIM | Close on one demonstrated result and one invitation; verify any pricing claims before reusing them. |

### Episode 2: prioritized edit map

| Source window | Decision | Editorial direction |
|---|---|---|
| 00:00–04:36 | CUT / REPLACE | Remove startup diagnostics and stream checks; begin with a concise binary + multiline promise. |
| 04:36–07:17 | KEEP / TIGHTEN | Explain the jobs and fixture. Shorten repository and command setup. |
| 07:17–09:05 | KEEP | Show the binary scanner, gzip decoding and output routing. |
| 09:05–10:50 | COMPRESS / VERIFY | Empty logs and receipt navigation: show the exact run ID and received payload. Earlier preparation runs are mentioned; do not silently present old output as this live run. |
| 10:50–12:05 | BONUS | Short binary recap; move subprocess documentation to a separate optional explanation. |
| 12:05–13:58 | KEEP / TIGHTEN | Explain timestamp boundaries and why a traceback must remain one event. |
| 13:58–14:18 | COMPRESS | Connection refusal before startup: one honest sentence, then show the pipeline running. |
| 14:18–16:30 | KEEP + PICKUP | Show grouped output. At about 15:15, RuntimeError: synthetic payment timeout is payload text, not evidence that this pipeline crashed. |
| 16:30–19:00 | TIGHTEN | Define benchmark workload, rate ladder and duration; remove chat-window switching. |
| 19:00–21:08 | KEEP + QUALIFY | Show the table, but qualify results as short runs on this hardware. CPU/disk causality needs separate measurement. |
| 21:08–25:55 | COMPRESS | Shell alias, script and node-restart troubleshooting: preserve the cause and recovery in 20–40 seconds, not the entire detour. |
| 25:55–27:25 | KEEP / TIGHTEN | JSON-transform result: at 27:05 table shows 966 and 5031 processed/s for targets 1000 and 5000. Report scope and duration, not maximum capacity. |
| 27:25–29:23 | TRIM | Keep repo link and a single result recap; end cleanly. |

### Pickups worth recording

- **Episode two, multiline:** “That exception is the synthetic log we are transporting. The output has line_count 5: the teaching point is that the five-line event stays together.” The frame at 15:15 and `sessions/002/simulate.py` corroborate the payload; this does not by itself prove every event was retained.
- **Episode two, receipt:** identify the job version, fresh run directory and output from that run. If the archive cannot establish the link, label the displayed file a reference result.
- **Episode two, benchmark:** “This is a short test of this workload on this machine. It is not a production capacity limit or an isolated CPU-versus-disk experiment.”
- **Episode one, schema:** replace the uncertain dead-letter explanation with the exact observed outcome. Do not claim destination receipt from an empty stdout panel.

### Presentation changes that matter

The sampled second-stream frames largely fill 16:9; the major issue is useful screen area, not a large persistent black border. Browser tabs and the debugging banner consume space. The low camera angle leaves much of the webcam inset showing ceiling/window and places the face near its bottom. Raise the camera to eye level, light the face, and reserve a camera area that cannot cover output. Episode one's framing is a better reference.

Use three prepared scenes: a brief presenter introduction, a large code view, and a result view with source and received records together. Enlarge the relevant predicate or record instead of showing an entire dashboard and expecting viewers to search it. Pause on the result long enough to read it. Keep chat on a separate device/window outside capture and take questions at chapter boundaries. Keep the node in a dedicated, labeled terminal so stopping a feed cannot accidentally stop the node.

### Review method and limits

Both files were inspected through frames sampled every 30 seconds across their full timelines, selected full-resolution frames, local automatic transcription, and media/audio measurements. Episode two also has a successful Gemini 3.7 Flash static-video analysis. Episode one's Gemini processing failed across multiple inputs; no successful Gemini review is claimed for it. Automatic transcripts contained hallucinated repetition, so those passages were excluded and transcription was repeated with previous-text conditioning disabled. Transcripts are working evidence, not approved captions. This is not continuous frame-by-frame playback, a complete secret scan, or lip-sync certification. Model suggestions were checked and narrowed where they exceeded the evidence.

## Proposed third episode

**Working title: Cut log noise without losing the incident.**

Audience: an operator who needs to reduce forwarded routine logs but cannot afford to hide known incidents. Promise: define which records matter, filter at the edge, and prove that the expected incident IDs arrived.

Use one fixed synthetic feed for the whole episode. A proposed fixture is 100 uniquely identified events: 90 routine events, six warnings, two errors, and two slow requests at ordinary severity. These are fixture-design counts, not measured results or a production savings claim. Preserve a separate expected-ID manifest before the pipeline runs.

The deliberate mistake removes the slow-request condition. Eight expected events should arrive and the two known slow-request IDs should be missing. Restore the condition, deploy a new version through Cloud, replay the same fixture into a fresh run-specific destination, and prove all ten expected IDs arrived. Verify exact IDs, no unexpected IDs, and duplicates as well as counts. Measure serialized bytes separately; a 90% reduction in record count is not necessarily a 90% byte reduction.

### Proposed 22-minute run

| Time | Presenter action | What the audience can verify |
|---|---|---|
| 0:00–0:45 | Show the intended result and state the incident-retention question | A clearly labeled reference result; do not imply it is the new live run |
| 0:45–3:00 | Show the fixed feed and independent incident list | 100 IDs, 10 expected incidents, and why each must survive |
| 3:00–7:00 | Read the short keep predicate and deploy through Cloud | Job version, execution, selected node, then destination records |
| 7:00–10:00 | Compare the input and received ID sets and bytes | Defined filtering vs unexpected loss |
| 10:00–14:00 | Remove the slow-request condition and deploy | Two known slow events disappear; the contract fails visibly |
| 14:00–18:00 | Restore, deploy, and replay into a fresh destination | All expected incident IDs arrive; counts and duplicates are checked |
| 18:00–20:00 | Explain the limits | Fixture-specific result, filtered routine records, untested outage/production behavior |
| 20:00–22:00 | Recap and take a constrained audience variation | One threshold change, a prediction, and a check |

### What to build first

- Reuse the Cloud deployment and TCP feed/watcher pattern from `sessions/002/demo.py`.
- Adapt the predicate in `vendor/benchmarking/scenarios/filter-90.yaml` into the teaching pipeline. Its current `reason` mapping labels a warning without an error/5xx condition as `slow`; fix that classification before using it on screen.
- Add a deterministic fixture, independent expected-ID manifest, run IDs, separate output files, and a receipt verifier. Those episode-three assets do not exist yet.
- Make source, retained results, and missing expected IDs legible in one 16:9 presentation area. Show node logs only for diagnosis and Cloud state only when proving deployment/execution. Keep any presenter web UI localhost-only.
- Rehearse the exact intended failure and recovery. If a different failure occurs, identify it honestly and use a labeled saved result after a bounded diagnosis rather than treating it as the planned demonstration.

Two alternatives are schema-change/dead-letter recovery, which needs replay and duplicate handling that the current example lacks, and a controlled throughput comparison, which has more reusable code but gives the audience less immediate visual feedback. The filtering episode has the clearest single decision and visible failure.

## Recording procedure for episode three

1. Enable **Automatically record when streaming**. Decide whether recording should continue after streaming stops for an outro or pickup, and explicitly stop it afterward.
2. Retain a 3840 × 2160 canvas and recording output, a separate hardware recording encoder, MKV, and a 1920 × 1080 streaming rescale. For predominantly terminal/browser teaching, rehearse 4K30 recording and 1080p30 streaming as a lower-load alternative to 60 fps. Do not assume that change alone fixes the measured rendering lag.
3. Size the presentation windows to 16:9, select those exact windows in OBS, and fit each source. Check the source capture mode: application/display capture may include more than the intended window. Select a specific window or crop deliberately; preserve its aspect ratio rather than stretching it.
4. Record a short rehearsal with the actual demo workload and both intended encoders active. Check OBS Stats, voice level, readability, frame pacing, and the resulting file with FFprobe. The earlier 13-second recording and separate stream did not test simultaneous streaming and recording.
5. Before teaching, visibly confirm that both STREAM and REC timers are advancing. Keep an unobtrusive recording-status check in the presenter routine.
6. At the end, say the result in one clean sentence, pause, stop the stream, finish any pickup, then stop recording. Verify a file with the expected session duration, video, and audio exists before closing OBS. Remux MKV to MP4 for editing if needed; remuxing changes the container, not the image quality.

## Evidence files

`obs-evidence.txt`, `recording-verification.json`, `episode-001-media.json`, `episode-002-media.json`, and the loudness JSON files contain the bounded technical evidence. Video-analysis results and their confidence limits are retained separately. Source media remains under `source/`; no public upload or replacement video was published by this review.
