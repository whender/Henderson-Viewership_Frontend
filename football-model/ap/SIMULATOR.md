# Custom next-poll game results

Next Poll → Forecast basis → My game picks runs the published AP movement v3 model in the browser. Users can select a winner (initially 27–20), enter final scores, and apply their scenario. Unedited games retain the football model's default result assumptions. Picks remain available while switching AP views or forecast bases in the same page session; a new published snapshot resets them.

The editor includes upcoming games before the next poll cutoff involving at least one team in the default projected Top 40. This set stays fixed while editing. Completed games cannot be overridden. Both scores must be integers between 0 and 200, with no tie.

`export_ap.py` publishes `ap-simulator.json` alongside `ap.json`; the scheduled workflow commits both. The lazy-loaded, credential-free snapshot includes serialized trees, static prior-poll features, game context, and Vegas expectations. Matching timestamps, poll IDs, and model versions prevent mixing snapshots. The September 9 snapshot is approximately 217 KB before compression.

`src/apScenario.js` recalculates records, margins, opponent records, AP opponent buckets, Vegas residuals, peer comparisons, and comfortable-win calibration before scoring every candidate and returning the Top 40. It uses the same previously available poll and market inputs as the normal projection. Custom scores are hypothetical inputs, never stored as actual results.

`test_ap_simulator.py` checks all feature columns and rankings against Python for default and custom scenarios. Frontend tests cover default ranking/record parity, invalid scores, protected games, score entry, resets, snapshot mismatch, and restoring picks. Future model feature changes must update browser inference and retain this parity check.
