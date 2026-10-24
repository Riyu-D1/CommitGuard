---
name: frontend-design
description: Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults. Source: anthropics/skills (MIT/Apache).
license: Complete terms in LICENSE.txt (Anthropic skills repo)
---

# Frontend Design

Approach this as the design lead at a design studio known for giving every client a distinct visual identity that is not mistaken for anyone else's. This client has already rejected proposals that felt cliché or templated, and is paying for a distinctive point of view: make deliberate, opinionated choices about palette, typography, and layout that are specific to this brief, and take aesthetic risk if justified.

## Ground your designs in the subject matter

If the brief does not identify what the product or subject matter is, identify it yourself before designing. For CommitGuard: a fintech compliance product for finance/ops judges — dense pro-tool feel, evidence-first, calm confidence. The subject's industry, subject matter, and vernacular are where distinctive visual choices come from.

## Design principles

Typography carries the personality of the page. Choose typefaces deliberately, set a clear type scale with intentional weights, widths, and spacing. When type is used as a headline or visual element, use the type treatment itself as an active part of the design.

Default to line lengths of less than 80 characters. Serif typefaces can have slightly longer line lengths; give serif body text slightly more line-height than a sans-serif.

Avoid these default typographic treatments — the commonest tells of a generated page:
- Accenting just a single word or phrase in a headline (italic/bold/different color on one word).
- Using all caps for labels.
- Adding unnecessary typographic labels above content.

Visual structure is information. Structural devices like outlines, borders, numbering, eyebrows, dividers, labels encode useful information rather than decorate. Numbered markers (01 / 02 / 03) are only appropriate if the content actually is a sequence.

Use non-user-triggered motion sparingly — one orchestrated moment lands better than scattered effects. Motion that answers a person's action (opening, expanding, confirming) is welcome.

## Process: plan, review against the brief, build, critique

For calibration, AI-generated design right now clusters around these traits — treat them as defaults to avoid unless the brief demands them:
1. warm cream background with high-contrast serif display + terracotta accent;
2. near-black background with single acid-green/vermilion accent;
3. broadsheet layout with hairline rules and newspaper columns;
4. the SaaS-card kit: identical rounded cards, one radius everywhere, soft grey shadow, gradient washes;
5. template chrome: tracked-out ALL-CAPS eyebrow labels, 'A · B · C' meta strings, 'WORD — fragment' labels, tinted near-black, monospace data labels, '→' appended to links/buttons.

Work in two passes. First, a compact design plan: color (4–6 named hex values), type (faces + roles), layout (one-sentence prose + optional ASCII wireframe, with alignment guidance), principles. Then review the plan against the brief — if any part reads like the generic default, revise it and say why. Only then write code.

When writing CSS, be careful with selector specificity — type-based (.section) and element-based (.cta) selectors often cancel each other out with padding/margin.

## Restraint and self-critique

Spend boldness in one place. One memorable element; everything around it quiet and disciplined. Quality floor without announcing it: responsive, visible keyboard focus, reduced motion respected, accessible contrast. Take screenshots to review your own work if the environment supports it — a picture is worth 1000 tokens.

## Writing in design

Words exist to make the product easier to understand. Name things by what users understand ("Manage notifications", not "webhook config"). Active voice; a CTA says exactly what happens ("Save changes", not "Submit"). Errors explain what went wrong and how to fix it — never apologize, never vague. Sentence case, plain verbs, no filler. Each element does exactly one job.
