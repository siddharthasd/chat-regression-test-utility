## Style Guidelines

- Use semantic HTML5 elements (`<header>`, `<main>`, `<section>`, `<article>`, `<footer>`)
- Mobile-first CSS. Use media queries to scale up to wider viewports.
- CSS custom properties (`--var`) for colors and spacing to keep the theme consistent.

## Content Guidelines

- Do not use "—" as sentence breakers. Use a comma or a full stop to start a new sentence.
- Capitalise the first character of each word only for section titles and prominent headers.
- Language should be targeted towards the business user and not overly technical.

---

## Application Color Palette

These are the canonical colors for the harness UI. All new UI work must use these values. Do not introduce alternative shades for the same semantic role.

### Brand

| Role              | Value     | Usage                                      |
|-------------------|-----------|--------------------------------------------|
| Primary / brand   | `#7c3aed` | Navbar, buttons, links, active sidebar, row-links |
| Navbar shell      | `#1a1a2e` | Navbar and footer background (dark shell)        |
| Brand accent      | `#ffd740` | Navbar bottom border, accent highlights          |
| Surface / page    | `#eae5f2` | Page background (lavender)                       |
| Card / panel      | `#ffffff` | Elevated cards (use `.harness-card`)             |
| Table header      | `#f5f3fb` | Table `<th>` background                          |
| Border            | `#e2dcf5` | Card borders, table rules (purple-tinted)        |

### RAG Status Colors

These three values are the single source of truth for Red / Amber / Green across the entire application. Use them for status badges, verdict indicators, alert borders, test-result cards, progress bars, and any diagram that encodes app states.

| Status  | Color     | Usage                                                        |
|---------|-----------|--------------------------------------------------------------|
| Green   | `#198754` | Pass verdict, Completed badge, ok indicator, success state   |
| Amber   | `#fd7e14` | Warn verdict, Completed-with-errors badge, unexpected dims   |
| Red     | `#dc3545` | Fail verdict, Failed badge, error indicator, alert borders   |

### Supporting Status Colors

| Role                  | Color     | Usage                                           |
|-----------------------|-----------|-------------------------------------------------|
| Queued                | `#0d6efd` | Queued job badge                                |
| Running               | `#0dcaf0` | Running job badge (dark text on this background)|
| Cancelling            | `#ffc107` | Cancelling badge (dark text on this background) |
| Draft / Cancelled     | `#6c757d` | Draft and cancelled job badges                  |
| Archived              | `#adb5bd` | Archived badge (dark text on this background)   |

### Alert / Notice Borders

| Role        | Border color | Background      |
|-------------|--------------|-----------------|
| Error alert | `#dc3545`    | Bootstrap danger |
| Notice      | `#0dcaf0`    | Bootstrap info   |

### Test-Connection Results

| Result              | Border     | Background  |
|---------------------|------------|-------------|
| OK                  | `#198754`  | `#d1e7dd`   |
| Error               | `#dc3545`  | `#f8d7da`   |
| Timeout             | `#fd7e14`  | `#fff3cd`   |
| Auth failure        | `#ffc107`  | `#fff3cd`   |

---

## Architecture Diagram Style Guidelines

### General Philosophy

- Diagrams must be clean, flat, and minimal. No gradients, drop shadows, or decorative effects.
- Every element earns its place. Remove anything that does not encode information.
- Diagrams communicate structure and relationships, not decoration.

### Canvas and Layout

- SVG viewBox: `0 0 900 600` for landscape, `0 0 700 800` for portrait (adjust to content)
- Outer padding: 40px on all sides. Never let elements touch the edge.
- Group related components into clearly separated swim lanes or zones.
- Align elements to an invisible grid (multiples of 20px for x/y positions).
- Flow direction: left-to-right (preferred) or top-to-bottom. Never mix directions.

### Boxes and Shapes

- Standard box size: **120–160px wide × 44–56px tall** for components
- Large containers (clusters/groups): rounded rect with a subtle fill and a label at the top-left
- Corner radius: `rx="6"` for standard boxes, `rx="10"` for containers
- Border: `1.5px` stroke, never bold borders
- No filled backgrounds with strong color. Use light tints (`opacity: 0.08–0.15`) or white/near-white fills.
- Distinguish box types by shape or border style, not just color:
  - Service/component: rectangle
  - External system: rectangle with dashed border
  - Database: cylinder or rectangle with `⬡` icon prefix
  - Queue/bus: rectangle with parallel-line icon
  - User/actor: circle or stick figure

### Spacing

- Minimum gap between boxes: **40px horizontal, 36px vertical**
- Within a cluster/group: **24px internal padding**
- Between clusters: **60px or more**
- Label-to-box gap: **6–8px**

### Colors

Use at most **2 color ramps** per diagram (e.g. blue for your system, grey for external). All fills must be light tints only. Strokes use the application's canonical RAG palette below — never introduce a new color for a role already covered.

| Role               | Fill          | Stroke    | Notes                                  |
|--------------------|---------------|-----------|----------------------------------------|
| Primary subject    | `#e8ecf8`     | `#1a237e` | Brand navy — your system's components  |
| Secondary / support| `#f0f4f0`     | `#5a7a5a` | Supporting components                  |
| External / passive | `#f5f5f5`     | `#999999` | Out-of-scope or third-party systems    |
| Warning / risk     | `#fff3cd`     | `#fd7e14` | RAG Amber — matches app warn color     |
| Negative / stop    | `#f8d7da`     | `#dc3545` | RAG Red — matches app fail/error color |
| Success / positive | `#d1e7dd`     | `#198754` | RAG Green — matches app pass color     |
| Neutral container  | none / `#fafafa` | `#cccccc` dashed | Grouping containers            |

Add a 1-line legend if color encodes meaning (tier, state, ownership).

### Typography

- Font family: `'Segoe UI', system-ui, -apple-system, sans-serif`
- Box labels: **12–13px**, `font-weight: 500`, centered
- Sub-labels / type hints: **10px**, `font-weight: 400`, `fill: #666`
- Section/cluster labels: **11px**, `font-weight: 600`, `letter-spacing: 0.04em`, `text-transform: uppercase`
- Diagram title: **14px**, `font-weight: 600`
- Never exceed **14px** for any label inside the diagram.
- Truncate long names with ellipsis rather than shrinking font below 10px.

### Arrows and Connectors

- Stroke width: `1.5px` for standard flows, `2px` for primary/critical paths
- Arrow color: `#555` (neutral) or match source node's color ramp
- Arrowhead: small filled triangle marker (`markerWidth="6" markerHeight="6"`)
- Use orthogonal (right-angle) connectors where possible. Avoid diagonal lines.
- Add a short text label on connectors only when the relationship is non-obvious. Keep it to 3 words or fewer, 10px, `fill: #777`.
- Bidirectional flow: use `marker-start` and `marker-end` on a single line, not two overlapping lines.
- Async/event-driven links: dashed stroke (`stroke-dasharray="5,4"`)
- Avoid connector crossings. Reroute paths around boxes instead.

### Icons and Symbols

- Use simple 16×16 or 20×20 SVG path icons (no external image URLs).
- Place icons left of the label, vertically centered within the box.
- Icon stroke matches box stroke color. Keep icon strokes at 1.5px.

### Density Rules

- Maximum **4 boxes** in a single horizontal row at full width. Wrap or split into sub-diagrams beyond that.
- Maximum **~20 nodes** per diagram. Split complex systems into overview and detail views.
- If a diagram needs a legend, keep it to 5 entries or fewer in a compact row at the bottom.

### Anti-Patterns to Avoid

- No rainbow color schemes
- No bold/heavy fonts inside boxes
- No overlapping elements
- No connector spaghetti. Reroute or split the diagram.
- No all-caps box labels (only section headers use uppercase)
- No icon dumps. Icons are optional. Use them only when they add clarity.

---

## General Diagram Style Guidelines

### Philosophy

- Diagrams teach one idea at a time. If a diagram needs a paragraph to explain itself, split it.
- Flat, clean, minimal: no gradients, drop shadows, textures, or decorative flourishes.
- Visual hierarchy replaces verbal explanation. The eye should move in the intended reading order.
- Consistency across all diagrams in the same document is mandatory. Never mix styles.

### Canvas and Layout

- SVG viewBox: `0 0 900 560` landscape (default), `0 0 660 800` portrait
- Outer padding: 40px on all sides. No element touches the edge.
- Reading direction: left-to-right or top-to-bottom. Establish one and hold it.
- Align all elements to a 20px grid (positions as multiples of 20).
- Group related elements spatially. Use whitespace as a separator before reaching for borders.
- Place the diagram title top-left at 40px, 28px. Legend (if needed) bottom-left.

### Shapes and Sizing

#### Standard shapes and their meanings — use consistently across all diagrams:

| Shape              | Meaning                                      |
|--------------------|----------------------------------------------|
| Rectangle          | Process, component, concept, entity          |
| Rounded rectangle  | State, stage, phase                          |
| Diamond            | Decision / branch point                      |
| Circle / oval      | Start / end terminal, actor                  |
| Parallelogram      | Input / output / data                        |
| Cylinder           | Storage / database                           |
| Dashed rectangle   | External system, out-of-scope                |
| Bold outline rect  | Emphasis / primary subject                   |

#### Sizing

- Standard node: **130–160px wide × 44–54px tall**
- Small/leaf node: **100–120px wide × 36–44px tall**
- Large container/group: sized to contents plus 24px internal padding on all sides
- Decision diamond: **70×70px**
- Terminal circle: **44×44px**
- Corner radius for rounded rects: `rx="8"`. For containers: `rx="12"`.

### Spacing

- Minimum gap between any two nodes: **40px horizontal, 36px vertical**
- Inside a container/group: **24px internal padding**
- Between groups or swim lanes: **56px or more**
- Connector label clearance: **8px** from the line to the label text
- Section title to first element: **20px**

### Color System

Use at most **2 color ramps** per diagram. 3 only when encoding three distinct categories. All fills must be light tints only. Strokes and fills follow the application's canonical RAG palette — the same values used in the UI.

| Role               | Fill       | Stroke    |
|--------------------|------------|-----------|
| Primary subject    | `#e8ecf8`  | `#1a237e` |
| Secondary / support| `#f0f4f0`  | `#5a7a5a` |
| External / passive | `#f5f5f5`  | `#999999` |
| Warning / risk     | `#fff3cd`  | `#fd7e14` |
| Negative / stop    | `#f8d7da`  | `#dc3545` |
| Success / positive | `#d1e7dd`  | `#198754` |
| Neutral container  | none / `#fafafa` | `#cccccc` dashed |

Color must encode meaning, not decoration. If two boxes are the same category, give them the same color. Add a legend whenever color encodes category (max 5 entries, compact row, bottom of canvas).

### Typography

- Font: `'Segoe UI', system-ui, -apple-system, sans-serif`
- All text is anti-aliased SVG. Never rasterize labels.

| Role                  | Size  | Weight | Color     | Style                               |
|-----------------------|-------|--------|-----------|-------------------------------------|
| Diagram title         | 15px  | 600    | `#1a1a2e` | —                                   |
| Node / box label      | 12px  | 500    | `#1a1a2e` | Centered                            |
| Node sub-label / type | 10px  | 400    | `#666666` | Centered                            |
| Connector label       | 10px  | 400    | `#666666` | —                                   |
| Section / lane header | 11px  | 600    | `#555555` | Uppercase, letter-spacing 0.05em    |
| Legend entry          | 10px  | 400    | `#444444` | —                                   |
| Annotation / callout  | 10px  | 400    | `#555555` | Italic                              |

- Hard cap: 15px maximum for any text in a diagram.
- Never go below **10px**. Truncate with ellipsis instead of shrinking.
- No all-caps node labels. Only section/lane headers use uppercase.
- Line-wrap long labels at ~18 characters using `<tspan dy="1.2em">`.

### Arrows and Connectors

- Default stroke: `1.5px`, color `#555555`
- Primary / critical path: `2px`, color matching the node's stroke ramp
- Arrowhead: small filled triangle marker, `markerWidth="6" markerHeight="6"`, `refX="5"`

| Flow type         | Style                              |
|-------------------|------------------------------------|
| Sequential        | Solid line, single arrowhead       |
| Bidirectional     | Solid line, arrowhead both ends    |
| Optional / weak   | Dashed `stroke-dasharray="5,4"`    |
| Async / event     | Dashed `stroke-dasharray="6,3"`    |
| Inheritance / is-a| Solid line, hollow triangle head   |
| Dependency / uses | Dotted `stroke-dasharray="2,3"`    |

- Prefer **orthogonal (right-angle) routing** over diagonal lines.
- Connectors enter/exit boxes at the center of a side, not corners.
- Avoid crossings. Reroute around boxes if needed.
- Label connectors only when the relationship is non-obvious. Keep labels to 3 words or fewer.

### Diagram Types — Specific Rules

#### Flowchart

- Flow goes top-to-bottom or left-to-right. Pick one per diagram.
- Decision diamonds have exactly 2 exits: label them Yes/No or True/False, always.
- Start and end terminals are filled circles (start: dark fill, end: double circle or dark ring).
- Merge paths reconverge at a small junction dot or an unlabeled process box.

#### Sequence Diagram

- Lifelines: vertical dashed lines, `stroke-dasharray="4,4"`, `1px` stroke, `#aaaaaa`
- Actor boxes (top): 120×36px, same typography as standard nodes
- Messages: horizontal arrows between lifelines, labeled, 12px font
- Activation bars: 10px wide rect on the lifeline, light fill `#d0e4ff`
- Time flows strictly downward. Label time steps on the left margin if needed.

#### Entity-Relationship / Data Model

- Entities: plain rectangles. Attributes listed inside as 10px lines.
- Primary key: underlined attribute label
- Relationships: labeled diamond or labeled connector. Cardinality noted (`1`, `N`, `0..1`).
- Keep attribute lists to 5 or fewer per entity. Use "..." for omitted fields.

#### State Machine

- States: rounded rectangles
- Initial state: filled black circle. Final state: filled circle inside a ring.
- Transitions: curved or orthogonal arrows, labeled with `event [guard] / action`
- Group sub-states inside a dashed rounded container.

#### Concept / Mind Map

- Central concept: larger box (180×56px), primary stroke color, slightly bolder label
- First-level children: standard boxes, connected with `2px` lines radiating outward
- Second-level: small boxes, `1px` lines. Go no deeper than 2 levels in a single diagram.
- Arrange children symmetrically. Balance left and right sides.

#### Timeline

- Single horizontal baseline: `2px` solid `#cccccc`
- Milestone marker: filled circle on the baseline, 8px radius
- Label above and below alternately to avoid overlap. 12px, left-aligned.
- Time axis labels: 10px, `#888888`, centered under markers

### Density and Splitting Rules

- Max nodes per diagram: **20**. Beyond that, split into overview and detail views.
- Max **4 items in a horizontal row** at full canvas width. Wrap or create a second row.
- If a legend would exceed 5 entries, the diagram has too many categories. Simplify.
- If connectors cross more than twice, restructure the layout before adding more nodes.
- Prefer two focused diagrams over one cluttered diagram.

### Anti-Patterns — Never Do These

- Rainbow color schemes (more than 2–3 ramps)
- Saturated or dark background fills on nodes
- Font sizes above 15px or below 10px
- Diagonal connectors in flowcharts or sequence diagrams
- Connector spaghetti — more than 2 lines crossing
- All-caps node labels
- Decorative icons that do not encode meaning
- Shadows, glows, gradients, or embossing
- Mixing shape conventions within one diagram (e.g. diamond used for both decision and storage)
- Omitting arrowheads on directed flows
- Unlabeled decision branches

### Reuse Checklist (apply before finalising any diagram)

- [ ] Reading direction is consistent and obvious
- [ ] All shapes follow the standard shape-meaning table
- [ ] No more than 2 color ramps. Legend present if color encodes category.
- [ ] No font exceeds 15px. No font below 10px.
- [ ] All directed connectors have arrowheads
- [ ] Decision branches are labeled
- [ ] Element count ≤ 20. Spacing ≥ 36px vertical, 40px horizontal.
- [ ] Outer padding ≥ 40px. Nothing touches the canvas edge.
- [ ] Title present top-left. Legend (if needed) bottom-left.
