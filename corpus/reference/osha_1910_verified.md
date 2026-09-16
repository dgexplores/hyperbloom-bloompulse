# Verbatim reference text for passages marked `**Provenance:** published`

This directory exists so `span_fidelity` can mean something. The corpus files in
`corpus/sources/` are parsed into citations, and a test checks each span appears
in the file it was parsed from — which is circular, because a paraphrase or an
invention written into that file passes just as easily as a real quote.

The text below was copied by hand from the source URLs, on the date recorded
against each passage in `corpus/sources/`. The test
`test_published_spans_are_verbatim_in_the_reference_text` requires every span
marked published to appear verbatim here.

**What this does and does not prove.** It proves a published span matches a
checked-in copy of the source text, so a paraphrase cannot sit behind a
`published` marker unnoticed, and any later edit to a published span fails the
suite. It does not by itself prove the checked-in copy matches the live
regulation — that is a human act of copying, recorded by date. To re-verify,
fetch the URL and diff it against the passage below. Anyone reading a citation
can now audit the claim in one step instead of taking the marker on trust.

Passages marked synthetic (the default) are exempt: they are demo-written by
definition and make no claim to be published text.

---

## OSHA 29 CFR 1910.147(a)(3)(i) — Purpose

Source: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147
Copied: 2026-09-17

This section requires employers to establish a program and utilize procedures
for affixing appropriate lockout devices or tagout devices to energy isolating
devices, and to otherwise disable machines or equipment to prevent unexpected
energization, start-up or release of stored energy in order to prevent injury to
employees.

Note: the corpus previously carried a stitched paraphrase here that read
"energy isolating mechanisms" and elided two paragraphs with an ellipsis. The
regulation says "energy isolating devices", and the sentence begins "This
section requires employers to", not "The employer shall".

---

## OSHA 29 CFR 1910.212(a)(1) — Types of guarding

Source: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212
Copied: 2026-09-17

One or more methods of machine guarding shall be provided to protect the
operator and other employees in the machine area from hazards such as those
created by point of operation, ingoing nip points, rotating parts, flying chips
and sparks. Examples of guarding methods are - barrier guards, two-hand
tripping devices, electronic safety devices, etc.

---

## OSHA 29 CFR 1910.212(a)(5) — Exposure of blades

Source: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.212
Copied: 2026-09-17

When the periphery of the blades of a fan is less than seven (7) feet above the
floor or working level, the blades shall be guarded. The guard shall have
openings no larger than one-half (½) inch.

Note: the corpus previously filed this passage under 1910.219(p). It is not in
1910.219 at all — that paragraph is "Care of equipment" — and 1910.219 covers
power-transmission apparatus, not fan guarding.
