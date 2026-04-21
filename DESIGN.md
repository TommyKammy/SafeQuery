# SafeQuery Design Contract

## Provenance

Source inspiration: https://getdesign.md/playstation/design-md

This contract is inspired by the PlayStation direction and is not an official PlayStation design system. It adapts the source direction for SafeQuery's enterprise NL2SQL product shell, replacing console-retail cues with a review-first data product posture. SafeQuery-specific adjustments include denser information framing, stricter surface separation for query review flows, and more restrained cyan accents so the UI reads as governed tooling rather than entertainment marketing.

Vanna-provided UI surfaces are out of scope for this contract. SafeQuery must present an application-owned product shell that remains valid even if the SQL generation adapter changes.

## Product Intent

Build a dark, product-forward shell that feels precise, calm, and premium rather than playful. The interface should communicate controlled power: strong hierarchy, minimal ornament, and enough contrast to support long review sessions without turning into neon cyberpunk styling.

This contract defines the visual design language that supports the workflow model in [docs/design/operator-workflow-information-architecture.md](./docs/design/operator-workflow-information-architecture.md). The architecture doc defines which regions and workflow states must exist. This file defines how those regions should look, feel, and prioritize attention.

The visual model is a three-surface layout:

1. Frame surface for app chrome, navigation, and persistent status.
2. Primary work surface for the active task, such as query composition, SQL preview, or result review.
3. Secondary support surface for metadata, audit context, guidance, and system status.

Do not collapse these three roles into a single flat canvas. Users should always be able to tell what is structural chrome, what is the main task area, and what is supporting context.

## Workflow-First Shell Posture

SafeQuery is an operator shell, not a chat transcript.

- The left rail history is persistent workflow memory, not a transcript surface.
- Source identity must stay visible in the frame or support surfaces across every workflow state.
- The main work surface should emphasize one dominant job at a time: Question composition, SQL preview, Guard review, or Result inspection.
- Support surfaces should keep reviewed context visible, including source status, guard posture, candidate metadata, and audit anchors.
- Results must not replace review context. When results appear, the operator should still be able to verify what was reviewed and why execution was allowed or blocked.
- If source binding, candidate identity, guard posture, or execution eligibility signals are missing, the shell should stay visually fail-closed instead of implying that execution can proceed.
- Attachments are out of scope for the UX-1 MVP. Do not present live upload, drag-and-drop intake, or an implied attachment pipeline in the shell until a later governed issue set defines that workflow.

## Color System

Base the system on near-black neutrals with cool undertones.

- App background: `#070b14`
- Frame surface: `#0c1220`
- Primary panel: `#101a2c`
- Secondary panel: `#152238`
- Elevated overlay: `#1b2a45`
- Strong border: `#2a3d61`
- Soft border: `rgba(163, 191, 250, 0.16)`
- Primary text: `#f5f7fb`
- Secondary text: `#b4bfd3`
- Muted text: `#7f8ca6`
- Cyan accent: `#3fd0ff`
- Cyan hover glow: `rgba(63, 208, 255, 0.24)`
- Success: `#4fd18b`
- Warning: `#f0c15b`
- Danger: `#ff6b7a`

Usage rules:

- Cyan is reserved for interactive emphasis, focus states, active navigation, selected rows, progress affordances, and links. Do not use cyan as a large background fill.
- Status colors must remain subordinate to the neutral shell. They should mark state, not restyle the page.
- Large surfaces should stay matte and dark. Use gradients sparingly and only for hero framing or page-level atmosphere.
- Keep gradients subtle: cool deep-blue blends are acceptable, but visible rainbow or purple-heavy treatments are not.

## Typography

Use a high-contrast display face for major titles and a plain sans-serif for operational UI text.

- Display family: `"Sora", "Avenir Next", "Segoe UI", sans-serif`
- Body family: `"Inter", "Segoe UI", sans-serif`
- Code family: `"JetBrains Mono", "SFMono-Regular", monospace`

Type scale:

- Hero or landing headline: `clamp(2.75rem, 5vw, 4.5rem)`, weight 600, tight tracking
- Section headline: `1.5rem` to `2rem`, weight 600
- Panel title: `1.125rem` to `1.25rem`, weight 600
- Body copy: `0.95rem` to `1rem`, weight 400
- Metadata and labels: `0.78rem` to `0.84rem`, weight 500, slight positive tracking
- SQL, IDs, and audit values: `0.9rem`, monospace

Typography rules:

- Prefer short, strong display headlines instead of long marketing sentences.
- Body text should stay compact and operational.
- Use uppercase sparingly for eyebrow labels, tabs, and small control metadata only.
- Preserve generous contrast between display type and body type so the shell feels product-led, not document-like.

## Spacing and Rhythm

Use a disciplined 4px base grid with larger layout steps in 8px increments.

- Micro spacing: `4px`
- Control spacing: `8px`
- Dense stack spacing: `12px`
- Standard card spacing: `16px`
- Section spacing: `24px`
- Major layout spacing: `32px`
- Page gutters on desktop: `32px` to `40px`
- Page gutters on tablet: `24px`
- Page gutters on mobile: `16px`

Rhythm rules:

- Panels should feel intentionally padded but not airy; SafeQuery is a work product, not a marketing brochure.
- Use tighter vertical rhythm inside tables, logs, SQL previews, and audit lists.
- Keep major sections aligned to the same horizontal grid. Avoid staggered card edges and decorative offset layouts in core app screens.

## Surface Hierarchy

The shell should visually separate persistent structure from task content.

- Frame surface: global nav, environment switcher, workspace title, user/session status, and persistent controls
- Primary work surface: dominant task card or content column with the highest contrast and the largest title treatment
- Secondary support surface: narrower companion panels for guard results, evidence, metadata, and audit summaries

Surface rules:

- Each surface should have its own background token and border treatment.
- Default panel radius: `20px` for primary cards, `16px` for secondary cards, `999px` only for pills and segmented controls.
- Use light edge definition instead of heavy drop shadows. Shadows should be soft and short-range.
- Overlays and modals may brighten slightly, but they must stay within the same dark family.
- The active work surface should always be the brightest large surface on screen.

## Layout Contract

Use a three-zone composition on desktop:

- Left rail or top frame for navigation and persistent status
- Main content column for the active task
- Right support column for context, audit data, and secondary actions

Layout rules:

- Desktop target width: content should feel comfortable between `1280px` and `1440px`, with the main work column taking roughly 60 to 68 percent.
- Left rail history should feel narrower and structurally persistent, usually in the `240px` to `320px` range, so it reads as navigation memory rather than a second content canvas.
- Support columns should stay readable but clearly secondary.
- Source identity should stay pinned near the top of the frame or support context so the active scope is visible before the operator reads SQL, guard outcomes, or results.
- On pages without support content, keep the three-surface logic by allowing the secondary zone to collapse rather than turning the whole page into a uniform sheet.
- Landing or overview pages may use a bold hero, but application screens must quickly resolve into the operational three-surface shell.

## Component Treatment

Components should feel sharp, calm, and slightly premium.

- Buttons: solid dark or subtly tinted fills, medium-large height, clear label contrast, restrained cyan hover edge or glow
- Primary CTA: use cyan accent for border, text, or focused fill only when the action is the page's single dominant next step
- Inputs: dark filled fields with crisp borders, high placeholder contrast, and obvious focus ring
- Cards: broad radius, thin borders, subtle background separation, no glassmorphism blur
- History items: concise question summaries with visible source identity and lifecycle markers; selected or active items should use edge emphasis rather than a saturated fill
- Tables and lists: row separators more visible than card shadows; selected state uses cyan edge emphasis instead of a full bright fill
- Tabs and segmented controls: compact, tactile, and contrast-driven; active item may use cyan underline, pill, or inner glow
- Badges: muted neutral pills by default, colored only for state-bearing labels
- Source identity chips and metadata rows: compact, always legible, and clearly tied to the governed dataset or environment in scope
- Guard panels: structured severity, concise rationale, and explicit allow or blocked posture without ambiguous success styling
- Result panels: bounded data presentation with obvious labels for executed results versus advisory support context
- SQL previews and code blocks: darker inset surface, monospace text, visible line spacing, no decorative syntax theme that overwhelms the data

Interaction rules:

- Hover behavior should feel controlled. Favor slight scale, border brightening, or glow on actionable elements.
- Avoid bouncy motion, overshoot easing, or large parallax effects.
- Focus states must be keyboard-visible and should use cyan consistently.

## Tone and Interaction Emphasis

The shell should speak in calm operational language. It is a governed review tool, not an enthusiastic assistant persona.

- Prefer direct labels such as `Preview`, `Guard`, `Blocked`, `Ready to review`, and `Results` over conversational prompts or chat-like filler copy.
- Question composition can feel open-ended, but preview and review surfaces should feel exact, structured, and traceable.
- Execute or run actions must stay unavailable until the operator is reviewing a trusted preview state backed by the server-owned candidate record.
- When the system is blocked, missing a prerequisite, or waiting on trusted state, use explicit blocked styling and explanatory text instead of optimistic pending language.
- Result presentation should clearly distinguish executed data, source identity, and review metadata so operators do not confuse advisory context with result-backed evidence.
- Empty and no-result states should preserve the same workflow frame and continue to show source, preview, and guard context where available.

## Responsive Behavior

The aesthetic must survive compression without losing surface hierarchy.

- Desktop: preserve the full three-surface layout.
- Tablet: allow the support column to move below the main work surface, but keep chrome visually distinct from content panels.
- Mobile: reduce to a stacked flow of frame, primary task, then support panels while preserving surface color differences and panel radii.

Responsive rules:

- Do not flatten the UI into one continuous dark rectangle on smaller screens.
- Keep the main task surface first in the reading order after the top frame.
- Collapse navigation responsibly; preserve current-page identity and critical status in the top frame.
- Preserve source identity and workflow status ahead of expandable detail content at every breakpoint.
- Headlines may scale down, but display hierarchy must remain stronger than body copy at every breakpoint.
- Dense data views should prefer horizontal scrolling within a bounded panel over shrinking text below readable sizes.

## Implementation Guardrails

- Prefer CSS variables or design tokens for colors, radii, spacing, and type sizes before building page-specific styles.
- New frontend work should cite this file when introducing a major surface, component family, or page shell.
- Shell-level changes should stay aligned with [docs/design/operator-workflow-information-architecture.md](./docs/design/operator-workflow-information-architecture.md) and the candidate-based review and execution flow described in the ADR and design set.
- When a screen must choose between decorative similarity to the inspiration and SafeQuery clarity, choose clarity.
- If a proposed UI depends on engine-owned widgets, Vanna framing, or vendor-specific styling assumptions, reject it and restate the screen in SafeQuery-owned terms.
