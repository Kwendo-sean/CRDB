# Experience engine

`Experience` is the participant-facing envelope around a quiz, programme session, PAL challenge, expo activity, AIoT demonstration, survey, or custom challenge.

It controls title, slug, type, day, schedule, lifecycle, visibility, dashboard placement, registration/check-in requirements, points, cover asset, instructions, and theme. Domain-specific records remain authoritative: `Quiz` owns questions and competition behavior; `Session` owns attendance; `Activity` owns completion.

Lifecycle values are `DRAFT`, `SCHEDULED`, `LIVE`, `PAUSED`, `ENDED`, and `ARCHIVED`. The server determines availability. Frontend clocks may display a countdown but do not authorize entry or scoring.

Themes hold a controlled accent, background treatment, hero label, icon, intro copy, and result language. The seed creates four master-brand variants:

- infrastructure — systems/network language
- data — investigation and signal language
- fraud — forensic/case-file language
- finale — forecasting and grand-prize language

Themes alter narrative treatment without altering scoring rules or allowing arbitrary unreviewed branding.

The Control Room creation chooser routes quizzes and sessions into their dedicated builders. Expo activities, AIoT demos and custom challenges share the concise completion-experience form while retaining distinct `Experience.type` values, dashboard treatment and future extension points.
