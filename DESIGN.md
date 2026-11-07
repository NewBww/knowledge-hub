---
name: Knowledge Hub — Lexicon
description: A measured local knowledge reader with distinct navigation, index and reading surfaces.
colors:
  ink: "#282723"
  muted: "#656158"
  line: "#d7d2c8"
  oxblood: "#773c3e"
  oxblood-deep: "#602e30"
  rail: "#eeece5"
  index: "#f8f6f0"
  canvas: "#fffefa"
  selected: "#e4dfd4"
  selected-ink: "#592a2c"
  review-ink: "#754c1b"
  review-ground: "#f6f0e2"
  unresolved-ground: "#f6ecea"
  control-border: "#b9b3a8"
  hover-border: "#9c9284"
  hover-ground: "#e9e4da"
  review-border: "#bda780"
  unresolved-border: "#c4a4a4"
typography:
  brand:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "24px"
    lineHeight: 1.2
  evidence-heading:
    fontSize: "23px"
    fontWeight: 500
  index-page:
    fontSize: "17px"
    lineHeight: 1.35
  narrow-prose:
    fontSize: "18px"
  supporting:
    fontSize: "14px"
  introduction:
    fontSize: "16px"
  command:
    fontSize: "13px"
  display:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "clamp(30px, 3.3vw, 43px)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  prose:
    fontFamily: 'Georgia, "Times New Roman", serif'
    fontSize: "19px"
    lineHeight: 1.8
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "15px"
    lineHeight: 1.55
  heading:
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.35
  label:
    fontSize: "12px"
rounded:
  control: "4px"
  status: "3px"
spacing:
  control-inline: "12px"
  group: "16px"
  section: "28px"
  reader-inline: "40px"
components:
  button-primary:
    backgroundColor: "{colors.oxblood}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-primary-hover:
    backgroundColor: "{colors.oxblood-deep}"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 10px"
  navigation-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.selected-ink}"
---

# Design System: Knowledge Hub

## Overview

**Creative North Star: “Lexicon”** — the user-selected reader direction, preserved from the existing application. Navigation is familiar and quiet; knowledge gets a generous, measured reading column. Ivory surfaces and oxblood interactions distinguish the app without decorative book imagery or ornamental controls.

Use the system in ordinary daylight desktop and narrow-window reading. The interface is an operating surface around a document, not a dashboard or a chat transcript.

## Colors

Oxblood carries actions, links and focus. Warm neutral surfaces separate the workspace rail, index and reading canvas. Near-black is the primary reading ink; muted ink remains readable against every neutral surface.

**The Named State Rule.** Current, Needs review and Unresolved are explicit text labels. Amber and oxblood grounds reinforce those labels; color alone never communicates knowledge validity. Publication state and support freshness remain separate labels.

## Typography

Georgia and its local serif fallback own reading titles, book/page rows and prose. System sans owns navigation, forms, metadata and ordinary controls. Fonts are installed/system fonts; no remote font requests.

The title is fluid at the token-defined range. Section headings are smaller and semibold; body controls use the normal body size. Prose is 19px on desktop and 18px at narrow widths. Small metadata is supplementary, never the sole explanation of an error or permission.

Monospace is reserved for executable command examples, not used as a general technical costume. All source knowledge is rendered as inert text, including markup and command-like material.

## Layout

The desktop grid is a 220px view rail, 240px context index and a flexible reading canvas. The reading measure is capped at 70ch. Reader padding is 28px at the top, 40px inline, 72px at the bottom. The toolbar precedes the reading column; book context belongs there, not in a decorative label above the title.

At 861–1080px, navigation columns contract to 190px and 210px and reader inline padding becomes 28px. At 860px and below, the rail and index collapse behind a labelled Navigation disclosure. Content stays in one column with 24px inline padding, not a horizontally clipped miniature desktop.

Related fields and metadata stay grouped. A new section receives more space above its heading than below. Long names, locators, source prose and command examples wrap within the available width. No fixed-size attachment or image may widen the page.

## Elevation & Depth

Flat tonal separation, quiet one-pixel rules and whitespace establish hierarchy. There are no decorative shadows, texture overlays, glass surfaces or simulated paper. A visible focus outline is a state, not elevation.

## Shapes

Standard controls use small rounded corners; state labels are slightly tighter. Book/page rows and review comparisons use straight separators, not nested cards. Images keep their own content and aspect ratio; attachment previews are bounded and never masked into decoration.

## Components

- **Navigation:** Library is the persistent, visually leading Home entry; the shared Warehouse has no project-selection step. Books are presented as readable catalogue entries with purpose, overview, named state and explicit Open actions, not automatically replaced by the first page. Add knowledge and saved intake are contextual Library subflows; there is no Curator page. Settings groups optional Curator setup, shared knowledge-access consent and manual native update checks. Warehouse, review and attention remain secondary. Full-width text buttons use explicit `aria-current`; the active view is explicit. On narrow screens the labelled disclosure exposes both navigation columns, Escape closes it and restores focus.
- **Buttons:** a restrained solid primary action, bordered secondary actions and transparent navigation. Disabled states are visibly inactive; pending writes disable repeated submission. Keyboard focus uses a two-pixel oxblood outline with a three-pixel offset. Selection uses oxblood with light foreground; carets and scrollbars follow the same palette.
- **Inputs:** persistent labels, normal editable fields, a native mixed file/folder context selector and a separate bounded attachment flow. Source grants have named scope/status, per-job use checkboxes and explicit revocation; authorizing a root does not silently select it for every job. The capture starts with one textarea; attachment review is a linear list with a named Remove action. Full attachment names remain accessible even when the visible action says only Remove.
- **Reading:** book/page titles and sections lead. Support disclosures use native details/summary semantics; factual support is initially expanded and resolves to the shared Warehouse record, including cited/current revisions and freshness state.
- **Review:** explicit Before and After groups expose content, kind/publication, evidence, support and navigation changes. Human approval/rejection follows the comparison; stale decisions preserve the review and explain recovery.
- **Feedback:** inline alert/status messages, genuine empty/loading/denied states and recoverable input preservation. A saved capture or queued job is not presented as a successful model run. Activity distinguishes waiting, actual processing, blocked/stale work and ready-for-review proposals; durable work pauses on Quit and recovers on reopen.
- **Motion:** only small background-color transitions on navigation/rows, under `prefers-reduced-motion: no-preference`. Content is visible by default; no entrance animation delays reading.

## Do's and Don'ts

- **Do** preserve the selected Lexicon palette, system navigation and Georgia reading voice across Library, Warehouse, intake and review.
- **Do** keep context, publication state, freshness and permission scope explicit in text.
- **Do** use real native semantics, bounded media, wrapping text, keyboard focus and one-column narrow layouts.
- **Don't** replace the reader with dashboard tiles, chat bubbles or a default multi-field knowledge-creation form.
- **Don't** add decorative kickers, glyph-icon substitutes, gradients, ornamental borders, paper textures or unnecessary modals.
- **Don't** represent access enablement as proof of a connected harness or as a provider-privacy guarantee.
- **Don't** add remote assets, telemetry or model/provider controls to the reading surface. Optional bounded Curator setup belongs in Settings; it is not a general-purpose agent runner.
