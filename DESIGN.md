# BloomPulse design system

Recorded from the built surface, not written ahead of it. The direction
contract lives at the top of `frontend/index.html`. Product truth is in
`PRODUCT.md`.

## World

A multi-pen strip-chart recorder. The instrument this audience already reads,
rendered as a web surface. Chart stock, a printed grid, pens that draw, alarm
limits printed on the paper before any data arrives.

The governing idea: **a machine's condition is a continuous inked trace,
annotated where the event happened.** The surface refuses the category default,
a near-black telemetry dashboard built from a grid of glowing stat tiles.

Light, not dark. Chosen from the use scene rather than category habit: a
shop-floor office under fluorescent light and daylight, where the output gets
printed and carried to whoever holds the wrench. A print stylesheet exists for
exactly that reason.

## Color

Committed strategy. Chart stock owns the surface, and colour appears only where
it carries meaning. No colour is decorative.

| Token | Value | Role |
|---|---|---|
| `--paper` | `#F3F1E7` | Chart stock, the ground for the roll |
| `--paper-deep` | `#EAE7DA` | Body behind the roll, and ruled note fields |
| `--paper-edge` | `#DED9C7` | The roll's trimmed edge |
| `--grid-minor` | `rgba(196, 84, 53, 0.14)` | Printed minor grid |
| `--grid-major` | `rgba(196, 84, 53, 0.30)` | Printed major grid |
| `--ink` | `#17150F` | Printed text, warm near-black |
| `--ink-mid` | `#4C4634` | Secondary text, tinted from the paper hue |
| `--ink-soft` | `#6E6752` | Field labels and chart furniture |
| `--rule` | `#1C190F` | Structural rules |
| `--rule-hair` | `rgba(28, 25, 15, 0.22)` | Hairline dividers inside a block |
| `--pen-vib` | `#C01228` | Recorder pen 1, vibration. Also the primary action |
| `--pen-temp` | `#14654A` | Recorder pen 2, temperature |
| `--pen-press` | `#1C4C97` | Recorder pen 3, pressure |
| `--zone-ab` | `#14654A` | ISO 10816-3 Zone A/B, unrestricted |
| `--zone-c` | `#B07100` | ISO Zone C, and the abstain and synthetic markers |
| `--zone-d` | `#C01228` | ISO Zone D, shutdown |

Severity colour is never invented. It is the ISO zone the reading falls in, so
the verdict stamp and the chart's right margin always agree.

Secondary text is tinted from the paper's own hue rather than greyed.

## Type

| Token | Stack | Used for |
|---|---|---|
| `--furniture` | Archivo Narrow, Arial Narrow | Chart furniture, labels, numerals, buttons, the wordmark |
| `--prose` | Archivo, system-ui | Body text, findings, citation spans |

Chart furniture is uppercase, letterspaced `0.10em` to `0.15em`, and sized 9px
to 12px, which is how a recorder's printed labels behave. Body text runs 14px
to 15px at `1.55` line height, capped between `54ch` and `68ch`.

`font-variant-numeric: tabular-nums` is set on `body`. Every figure on this
surface is a measurement, and measurements must align in a column.

Two faces, one superfamily. Not a display serif, and not a monospace worn as a
costume for technical credibility.

## Structure

The page is one roll, `max-width: 1180px`, with trimmed edges and a consistent
inline padding. Structural separation is 2px rules, internal separation is 1px
hairlines. There are no cards, and no nested containers.

- **Header block.** Wordmark, one-sentence statement, and an instrument
  identification plate of four ruled fields.
- **Intake.** A ruled form field for the file, plus two sample actions.
- **Chart.** Pen range card above, the chart in a 1px frame, a note below.
- **Results.** Two columns divided by a rule. Condition and work order on the
  left, authority on the right. Collapses to one column under 860px.
- **Footer.** Disclaimer and provenance.

## The chart

Hand-drawn SVG, `viewBox="0 0 1000 320"`. No chart library.

The paper is pre-printed. Grid, ISO zone bands and both alarm limits render
before any data exists, so the empty state is a real blank chart rather than a
placeholder. Each pen carries its own engineering range and all three share one
0 to 100 percent grid, which is how a real multi-channel recorder works.

Positions come from elapsed time where timestamps parse, so a gap in the record
shows as a gap. Labels gain a date once a series runs past 24 hours.

Below 560px the chart scrolls horizontally at a `680px` minimum rather than
shrinking its 9px printed furniture into illegibility.

## Motion

One authored moment: the pens draw.

`stroke-dashoffset` over `1150ms` **linear**, staggered `90ms` per pen. Linear
is correct here and an ease-out would be wrong, because a chart recorder draws
at constant chart speed. Path length is measured on mount, since `pathLength`
normalisation does not reliably drive `stroke-dasharray`.

The event flag drops in at `1080ms`, after the pens have passed it, on
`cubic-bezier(0.2, 0.9, 0.3, 1)`.

Interface transitions are 60ms to 150ms. `prefers-reduced-motion` renders every
trace complete and still.

## Controls and state

Buttons are ruled rectangles in furniture caps. Hover inverts to ink on paper.
The primary action is filled in pen red. Focus is a 2px `--pen-vib` ring at
2px offset, and the drop zone carries `:focus-within` so the container shows
focus, not only the input inside it.

Every state is real and designed: empty (blank pre-printed chart plus a spec
table), loading (a sweep rule under the intake), error (a ruled notice naming
the problem and the recovery), abstain (a Zone C marker beside the confidence),
and synthetic (a Zone C marker on any corpus excerpt written for the demo).

## Rules this surface keeps

- No card grids, no nested containers, no section numbers, no eyebrows.
- No gradient text, no glass, no glow, no coloured side borders above 1px.
- No emoji or unicode glyphs standing in for icons. The chart is the only
  drawn element, and it is drawn to scale.
- Colour never decorates. It is a pen, a zone, or an action.
- Every number is tabular. Every claim shows its source.
