---
phase: 14-per-bot-profile-pictures
plan: 01
status: complete
requirements_completed: [IMG-01, IMG-02, IMG-03, IMG-04]
completed: 2026-10-21
---

# Phase 14 — panel profile pictures, v1.6.2

User explicitly clarified: pictures only in the panel. Added optional image_file metadata default blank for old profiles, ignored managed PNG assets and per-profile select/reset controls. Panel card and window icon follow the selected profile; fallback uses logo.png or an initial/generic icon without retaining another profile's image.

Import accepts PNG/JPEG/WebP/BMP, applies EXIF orientation, preserves alpha, crops to a bounded 512-square copy and writes atomically. Limits: 10 MB and 16 million source pixels. Managed UUID paths reject traversal/symlink escapes. Imported copy survives source-file removal.

Metadata-only setter reads latest registry under its lock, preserves current unrelated settings, and does not load/rotate tokens or call network APIs. Works for running bots and synthetic personal. Panel prevents overlapping form/autostart writes while image persistence runs; native file dialog captures original profile and late worker completion only refreshes that profile. Programmatic profile switching also updates selector text immediately.

Verification: 122 tests in 27 isolated modules passed; after final selector synchronization, all 18 affected desktop/profile UI tests passed. Seven new generated-image data tests and six new real-widget routing tests cover independent colors, select/reset, cancel, original-dialog target, late completion, failures, latest metadata, caps, alpha, EXIF and compatibility. Publication audit: zero findings; diff check clean; image directory ignored. Fake-profile panel screenshot visually inspected for image/button layout.

Independent review found no remaining blockers after generic icon fallback and native-dialog target capture corrections. Real user pictures/profile settings were not changed, Telegram avatars were not touched. Source phase 13 remains its own commit 16dd16f; this feature is committed separately, with no push or remote deployment.
