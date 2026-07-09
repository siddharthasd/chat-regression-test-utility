# HTML Artifact Style Guide

Use this guide when generating HTML/CSS artifacts in the Claude chat application.

---

## Accenture Brand Rules — MANDATORY

These rules take precedence over every other section in this guide. They must be applied without exception to every artifact generated for Accenture.

### Font

- Use **Arial only**. No other fonts — not Segoe UI, not system-ui, not Google Fonts.
- Font stack: `Arial, sans-serif`
- Headings: `font-weight: 700` (bold). Body copy: `font-weight: 400` (regular).

### Color palette

All colors must be drawn exclusively from the Accenture brand palette below. Do not introduce any other colors.

**Purple spectrum** (primary brand color family):

| Token                  | Hex       | Use                                      |
|------------------------|-----------|------------------------------------------|
| `--color-purple-deep`  | `#460073` | Dark accent, diagram strokes             |
| `--color-purple-dark`  | `#7500C0` | Mid-dark accent                          |
| `--color-primary`      | `#A100FF` | Primary UI color — tabs, links, accents  |
| `--color-purple-mid`   | `#C2A3FF` | Mid tint                                 |
| `--color-purple-light` | `#E6DCFF` | Card backgrounds, table headers, tips    |

**Neutrals** (60–70% of the visual surface):

| Token               | Hex       | Use                               |
|---------------------|-----------|-----------------------------------|
| `--color-black`     | `#000000` | Header bar background, text       |
| `--color-gray`      | `#818180` | Muted text, secondary labels      |
| `--color-gray-light`| `#CFCFCF` | Borders, dividers                 |
| `--color-neutral-bg`| `#F1F1EF` | Page background, alternate rows   |
| `--color-white`     | `#FFFFFF` | Surface, card backgrounds         |

**Secondary** (use sparingly, under 5% of visual surface, never for text):

| Hex       | Use                        |
|-----------|----------------------------|
| `#FF50A0` | Highlight accents only      |
| `#224BFF` | Highlight accents only      |

**Semantic** (retained for RAG status indicators only):

| Token              | Hex       |
|--------------------|-----------|
| `--color-warning`  | `#D97706` |
| `--color-warning-bg`| `#FEF3E2`|
| `--color-error`    | `#C0392B` |
| `--color-error-bg` | `#FEF0EF` |

### CSS custom properties — required root block

Every artifact must define these exact variables on `:root`:

```css
:root {
  --color-purple-deep:  #460073;
  --color-purple-dark:  #7500C0;
  --color-primary:      #A100FF;
  --color-purple-mid:   #C2A3FF;
  --color-purple-light: #E6DCFF;

  --color-black:        #000000;
  --color-gray:         #818180;
  --color-gray-light:   #CFCFCF;
  --color-neutral-bg:   #F1F1EF;
  --color-white:        #FFFFFF;

  --color-primary-bg:   #E6DCFF;
  --color-surface:      #FFFFFF;
  --color-border:       #CFCFCF;
  --color-text:         #000000;
  --color-text-muted:   #818180;
  --color-warning-bg:   #FEF3E2;
  --color-warning:      #D97706;
  --color-error-bg:     #FEF0EF;
  --color-error:        #C0392B;

  --space-xs:  8px;
  --space-sm:  16px;
  --space-md:  24px;
  --space-lg:  40px;
  --space-xl:  56px;
}
```

### Page background

Set `background: var(--color-neutral-bg)` on `body`. Content surfaces (cards, main panel) use `--color-white`.

### Header bar

The page header bar must use a black background with white title text and a 3px Accenture purple bottom border. Include the `>` symbol in `#A100FF` as a decorative element before the title.

```html
<div class="banner">
  <div class="banner-inner">
    <div class="banner-arrow">&gt;</div>
    <div class="banner-text">
      <h1>Page title here</h1>
      <p class="subtitle">Subtitle here.</p>
    </div>
  </div>
</div>
```

```css
.banner {
  background: #000000;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 3px solid var(--color-primary);
}
.banner-arrow { color: var(--color-primary); font-size: 32px; font-weight: 700; }
.banner-text h1 { color: #ffffff; font-size: 22px; font-weight: 700; }
.banner-text .subtitle { color: rgba(255,255,255,0.65); font-size: 13px; }
```

### Cards

Cards use a white background, subtle shadow, and 4–8px border radius. Do not use a general border on cards — the shadow provides the separation.

```css
.card {
  background: var(--color-white);
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}
.card--highlight {
  background: var(--color-purple-light);
  border-left: 4px solid var(--color-primary);
  border-radius: 0 8px 8px 0;
  box-shadow: none;
}
.card--warning {
  background: var(--color-warning-bg);
  border-left: 4px solid var(--color-warning);
  border-radius: 0 8px 8px 0;
  box-shadow: none;
}
```

### Headings

- Use **sentence case** for all headings. Capitalise only the first word and proper nouns.
- h1: 22px, bold. h2: 17px, bold. h3: 14px, bold.
- Heading font: Arial bold (`font-weight: 700`).

### Color proportions

- 60–70% neutral colors (black, grays, white, `#F1F1EF`).
- 30–40% purple (any shade from the purple spectrum).
- Under 5% secondary colors (`#FF50A0`, `#224BFF`). Never use secondary colors for text.

### Light mode only

All artifacts must use a white or light gray page background. Do not produce dark-mode or dark-background layouts.

---

## Technical Constraints

- HTML and CSS only. No JavaScript of any kind.
- No `<script>` tags, no `onclick` handlers, no event listeners.
- No external dependencies. No Google Fonts, no CDN links, no external images or stylesheets.
- Navigation between sections must use the radio button `:checked` CSS pattern. Do not use anchor links (they break inside SharePoint iframes).
- The file must work with zero internet connection.
- Set `html, body { width: 100%; }`. Do not use `min-height: 100vh`.
- All images must be embedded as base64 data URIs.
- The entire output is a single self-contained `.html` file with CSS embedded in a `<style>` block inside `<head>`.

---

## Language and Tone

- Write for a business audience. Avoid overly technical language.
- Do not use "—" as a sentence breaker. Use a comma or a full stop to start a new sentence.
- Capitalise the first character of each word for section titles and prominent headers only.
- Body copy uses standard sentence case.

---

## Layout

- Use semantic HTML5 elements: `<header>`, `<main>`, `<section>`, `<article>`, `<footer>`.
- Mobile-first CSS. Use media queries to scale up to wider viewports.
- Use CSS custom properties (`--var`) for all colors and spacing to keep the theme consistent.
- Outer page padding: `40px` on all sides. No content touches the viewport edge.
- Align content to a `20px` grid where possible.

---

## Color System

Define all colors as CSS custom properties on `:root`. Use at most two color ramps per page. Never use saturated fills as backgrounds on content blocks.

```css
:root {
  --color-primary:      #3B6FBC;
  --color-primary-bg:   #EBF3FF;
  --color-secondary:    #5A7A5A;
  --color-secondary-bg: #F0F4F0;
  --color-neutral-bg:   #F5F5F5;
  --color-surface:      #FFFFFF;
  --color-border:       #CCCCCC;
  --color-text:         #1A1A2E;
  --color-text-muted:   #666666;
  --color-warning-bg:   #FEF3E2;
  --color-warning:      #D97706;
  --color-error-bg:     #FEF0EF;
  --color-error:        #C0392B;

  --space-xs:  8px;
  --space-sm:  16px;
  --space-md:  24px;
  --space-lg:  40px;
  --space-xl:  56px;
}
```

---

## Typography

- Font stack: `'Segoe UI', system-ui, -apple-system, sans-serif`
- Never exceed `15px` for diagram labels. Body copy may go up to `16px`.
- Do not go below `10px` for any visible text.

| Role                | Size   | Weight | Color              |
|---------------------|--------|--------|--------------------|
| Page title (h1)     | 22px   | 600    | `--color-text`     |
| Section title (h2)  | 17px   | 600    | `--color-text`     |
| Sub-heading (h3)    | 14px   | 600    | `--color-text`     |
| Body copy           | 14px   | 400    | `--color-text`     |
| Muted / caption     | 12px   | 400    | `--color-text-muted` |
| Diagram node label  | 12px   | 500    | `--color-text`     |
| Diagram sub-label   | 10px   | 400    | `--color-text-muted` |

---

## Navigation (Radio Button Pattern)

Use hidden radio inputs and the `:checked` CSS selector to show and hide sections. Do not use anchor links.

```html
<!-- Inputs (hidden) -->
<input type="radio" name="nav" id="tab-overview" checked>
<input type="radio" name="nav" id="tab-details">

<!-- Nav bar -->
<nav>
  <label for="tab-overview">Overview</label>
  <label for="tab-details">Details</label>
</nav>

<!-- Sections -->
<section class="tab-panel" id="panel-overview"> ... </section>
<section class="tab-panel" id="panel-details"> ... </section>
```

```css
input[type="radio"] { display: none; }

.tab-panel { display: none; }

#tab-overview:checked ~ main #panel-overview,
#tab-details:checked  ~ main #panel-details  { display: block; }

nav label {
  cursor: pointer;
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 2px solid transparent;
}

#tab-overview:checked ~ nav label[for="tab-overview"],
#tab-details:checked  ~ nav label[for="tab-details"] {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
}
```

---

## General Diagram Rules

These rules apply to every SVG diagram in the document. Architecture diagrams and other specialised diagram types build on top of these foundations.

### Philosophy

- Each diagram teaches one idea. If it needs a paragraph to explain itself, split it into two.
- Flat, clean, minimal: no gradients, drop shadows, textures, or decorative flourishes.
- Visual hierarchy replaces verbal explanation. The eye should move in the intended reading order.
- All diagrams in the same document must be visually consistent. Never mix styles.

### Canvas and Layout

- ViewBox: `0 0 900 560` landscape (default), `0 0 660 800` portrait.
- Outer padding: 40px on all sides. No element touches the edge.
- Reading direction: left-to-right or top-to-bottom. Establish one and hold it throughout.
- Align all elements to a 20px grid (positions as multiples of 20).
- Group related elements spatially. Use whitespace as a separator before reaching for borders.
- Diagram title: top-left at `x=40, y=28`. Legend (if needed): bottom-left.

### Standard Shapes and Their Meanings

Use these shapes consistently across all diagrams. Never repurpose a shape for a different meaning within the same document.

| Shape              | Meaning                                  |
|--------------------|------------------------------------------|
| Rectangle          | Process, component, concept, entity      |
| Rounded rectangle  | State, stage, phase                      |
| Diamond            | Decision / branch point                  |
| Circle / oval      | Start / end terminal, actor              |
| Parallelogram      | Input / output / data                    |
| Cylinder           | Storage / database                       |
| Dashed rectangle   | External system, out-of-scope            |
| Bold outline rect  | Emphasis / primary subject               |

### Sizing

- Standard node: `130–160px wide`, `44–54px tall`.
- Small/leaf node: `100–120px wide`, `36–44px tall`.
- Large container/group: sized to contents plus 24px internal padding on all sides.
- Decision diamond: `70×70px`.
- Terminal circle: `44×44px`.
- Corner radius: `rx="8"` for rounded rects, `rx="12"` for containers.

### Spacing

- Minimum gap between any two nodes: 40px horizontal, 36px vertical.
- Inside a container/group: 24px internal padding.
- Between groups or swim lanes: 56px or more.
- Connector label clearance: 8px from the line to the label text.
- Section title to first element: 20px.

### Color System

Use at most 2 color ramps per diagram. 3 only when encoding three distinct categories. All fills must be light tints only. The same canonical RAG palette applies to all diagram types.

| Role               | Fill        | Stroke    |
|--------------------|-------------|-----------|
| Primary subject    | `#e8ecf8`   | `#1a237e` |
| Secondary/support  | `#f0f4f0`   | `#5a7a5a` |
| External/passive   | `#f5f5f5`   | `#999999` |
| Warning/risk       | `#fff3cd`   | `#fd7e14` |
| Negative/stop      | `#f8d7da`   | `#dc3545` |
| Success/positive   | `#d1e7dd`   | `#198754` |
| Neutral container  | `#fafafa`   | `#cccccc` dashed |

Color must encode meaning, not decoration. If two boxes belong to the same category, give them the same color. Add a legend whenever color encodes a category (max 5 entries, compact row, bottom of canvas).

### Typography

Font: `'Segoe UI', system-ui, -apple-system, sans-serif`. Hard cap: 15px for any text inside a diagram. Never go below 10px. Truncate with ellipsis instead of shrinking.

| Role                  | Size  | Weight | Color     | Style                            |
|-----------------------|-------|--------|-----------|----------------------------------|
| Diagram title         | 15px  | 600    | `#1a1a2e` |                                  |
| Node / box label      | 12px  | 500    | `#1a1a2e` | Centered                         |
| Node sub-label / type | 10px  | 400    | `#666666` | Centered                         |
| Connector label       | 10px  | 400    | `#666666` |                                  |
| Section / lane header | 11px  | 600    | `#555555` | Uppercase, letter-spacing 0.05em |
| Legend entry          | 10px  | 400    | `#444444` |                                  |
| Annotation / callout  | 10px  | 400    | `#555555` | Italic                           |

- No all-caps node labels. Only section/lane headers use uppercase.
- Line-wrap long labels at approximately 18 characters using `<tspan dy="1.2em">`.

### Arrows and Connectors

- Default stroke: `1.5px`, color `#555555`.
- Primary/critical path: `2px`, color matching the node's stroke ramp.
- Arrowhead: small filled triangle marker, `markerWidth="6" markerHeight="6"`, `refX="5"`.
- Prefer orthogonal (right-angle) routing over diagonal lines.
- Connectors enter and exit boxes at the center of a side, not corners.
- Avoid crossings. Reroute around boxes if needed.
- Label connectors only when the relationship is non-obvious. Keep labels to 3 words or fewer.

| Flow type          | Style                           |
|--------------------|---------------------------------|
| Sequential         | Solid, single arrowhead         |
| Bidirectional      | Solid, arrowheads both ends     |
| Optional/weak      | Dashed `stroke-dasharray="5,4"` |
| Async/event        | Dashed `stroke-dasharray="6,3"` |
| Inheritance/is-a   | Solid, hollow triangle head     |
| Dependency/uses    | Dotted `stroke-dasharray="2,3"` |

### Diagram-Type Rules

#### Flowchart

- Flow goes top-to-bottom or left-to-right. Pick one per diagram.
- Decision diamonds have exactly 2 exits, labeled `Yes`/`No` or `True`/`False`. Always.
- Start terminal: filled dark circle. End terminal: double circle or dark ring.
- Merge paths reconverge at a small junction dot or an unlabeled process box.

#### Sequence Diagram

- Lifelines: vertical dashed lines, `stroke-dasharray="4,4"`, `1px` stroke, `#aaaaaa`.
- Actor boxes (top): `120×36px`, same typography as standard nodes.
- Messages: horizontal arrows between lifelines, labeled, 12px font.
- Activation bars: `10px` wide rect on the lifeline, light fill `#d0e4ff`.
- Time flows strictly downward. Label time steps on the left margin if needed.

#### Entity-Relationship / Data Model

- Entities: plain rectangles. Attributes listed inside as 10px lines.
- Primary key: underlined attribute label.
- Relationships: labeled diamond or labeled connector. Cardinality noted (`1`, `N`, `0..1`).
- Keep attribute lists to 5 or fewer per entity. Use "..." for omitted fields.

#### State Machine

- States: rounded rectangles.
- Initial state: filled black circle. Final state: filled circle inside a ring.
- Transitions: curved or orthogonal arrows, labeled with `event [guard] / action`.
- Group sub-states inside a dashed rounded container.

#### Concept / Mind Map

- Central concept: larger box (`180×56px`), primary stroke color, slightly bolder label.
- First-level children: standard boxes, connected with `2px` lines radiating outward.
- Second-level: small boxes, `1px` lines. Go no deeper than 2 levels in a single diagram.
- Arrange children symmetrically. Balance left and right sides.

#### Timeline

- Single horizontal baseline: `2px` solid `#cccccc`.
- Milestone marker: filled circle on the baseline, `8px` radius.
- Label above and below alternately to avoid overlap. 12px, left-aligned.
- Time axis labels: 10px, `#888888`, centered under markers.

### Density and Splitting

- Maximum 20 nodes per diagram. Split into overview and detail views beyond that.
- Maximum 4 items in a horizontal row at full canvas width.
- If a legend would exceed 5 entries, the diagram has too many categories. Simplify first.
- If connectors cross more than twice, restructure the layout before adding more nodes.
- Prefer two focused diagrams over one cluttered diagram.

---

## Tables

Use standard HTML `<table>`. Keep headers short. Alternate row shading via `:nth-child(even)`. No JavaScript sorting.

```css
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th    { background: var(--color-primary-bg); color: var(--color-text); font-weight: 600; text-align: left; padding: var(--space-xs) var(--space-sm); }
td    { padding: var(--space-xs) var(--space-sm); border-bottom: 1px solid var(--color-border); }
tr:nth-child(even) td { background: var(--color-neutral-bg); }
```

---

## Cards and Panels

Use `<article>` or `<div>` with a consistent card style. No JavaScript toggling.

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}

.card--highlight {
  border-left: 4px solid var(--color-primary);
  background: var(--color-primary-bg);
}

.card--warning {
  border-left: 4px solid var(--color-warning);
  background: var(--color-warning-bg);
}
```

---

## Architecture Diagrams

Architecture diagrams follow the general SVG rules above and add the specific conventions in this section. Apply both sets of rules together.

### Canvas

- ViewBox: `0 0 900 600` for landscape, `0 0 700 800` for portrait. Adjust height to content.
- Outer padding: 40px on all sides. No element touches the edge.
- Flow direction: left-to-right (preferred) or top-to-bottom. Never mix directions in one diagram.
- Align all elements to a 20px grid.

### Boxes and Shapes

- Standard component box: `120–160px wide`, `44–56px tall`, `rx="6"`.
- Large containers/groups: rounded rect, subtle light-tint fill, label at top-left, `rx="10"`.
- Border: `1.5px` stroke. No bold borders.
- Fills: light tints only (`opacity: 0.08–0.15`). Never saturated or dark backgrounds.
- Distinguish box types by shape or border style, not color alone.

| Shape                     | Meaning                  |
|---------------------------|--------------------------|
| Rectangle                 | Service or component     |
| Rectangle, dashed border  | External system          |
| Cylinder or `⬡` prefix    | Database or storage      |
| Rectangle, parallel-line icon | Queue or bus         |
| Circle or stick figure    | User or actor            |

### Color Palette

Use at most 2 color ramps per diagram. Never introduce a new color for a role already covered below. All fills are light tints only.

| Role               | Fill        | Stroke    | When to Use                         |
|--------------------|-------------|-----------|-------------------------------------|
| Primary subject    | `#e8ecf8`   | `#1a237e` | Your system's own components        |
| Secondary/support  | `#f0f4f0`   | `#5a7a5a` | Supporting or internal services     |
| External/passive   | `#f5f5f5`   | `#999999` | Third-party or out-of-scope systems |
| Warning/risk       | `#fff3cd`   | `#fd7e14` | RAG Amber. Matches app warn color   |
| Negative/stop      | `#f8d7da`   | `#dc3545` | RAG Red. Matches app fail/error     |
| Success/positive   | `#d1e7dd`   | `#198754` | RAG Green. Matches app pass color   |
| Neutral container  | `#fafafa`   | `#cccccc` dashed | Grouping containers only      |

Add a legend at the bottom of the diagram whenever color encodes a category. Keep it to 5 entries or fewer in a single compact row.

### Spacing

- Minimum gap between boxes: 40px horizontal, 36px vertical.
- Within a cluster or group: 24px internal padding.
- Between clusters: 60px or more.
- Label to box gap: 6–8px.

### Typography (Architecture Diagrams)

- Font: `'Segoe UI', system-ui, -apple-system, sans-serif`.
- Box labels: 12–13px, `font-weight: 500`, centered.
- Sub-labels and type hints: 10px, `font-weight: 400`, `fill: #666`.
- Section and cluster labels: 11px, `font-weight: 600`, `letter-spacing: 0.04em`, `text-transform: uppercase`.
- Diagram title: 14px, `font-weight: 600`.
- Hard cap: 14px maximum for any label inside the diagram.
- Truncate long names with ellipsis rather than shrinking below 10px.

### Arrows and Connectors

- Standard flow: `1.5px` stroke, color `#555`.
- Primary or critical path: `2px` stroke, matching the source node's color ramp.
- Arrowhead: small filled triangle, `markerWidth="6" markerHeight="6"`.
- Prefer orthogonal (right-angle) routing. Avoid diagonal lines.
- Connectors enter and exit at the center of a box side, not a corner.
- Label a connector only when the relationship is non-obvious. Keep labels to 3 words or fewer, 10px, `fill: #777`.
- Bidirectional flow: use `marker-start` and `marker-end` on a single line, not two overlapping lines.
- Async or event-driven links: dashed `stroke-dasharray="5,4"`.
- Avoid crossings. Reroute around boxes when needed.

### Density

- Maximum 4 boxes in a single horizontal row at full canvas width.
- Maximum 20 nodes per diagram. Split into overview and detail views beyond that.
- Legend: 5 entries or fewer.

---

## Anti-Patterns — Never Do These

- No JavaScript of any kind.
- No external fonts, stylesheets, or image URLs.
- No anchor link navigation.
- No `min-height: 100vh` on `html` or `body`.
- No rainbow color schemes (more than 2–3 ramps).
- No saturated or dark background fills on content nodes.
- No font sizes above `15px` inside diagrams or below `10px` anywhere.
- No diagonal connectors in flowcharts.
- No connector crossings more than twice per diagram.
- No all-caps node labels inside diagrams.
- No decorative shadows, gradients, or glows.
- No mixing shape conventions within one diagram.
- No unlabeled decision branches in flowcharts.
