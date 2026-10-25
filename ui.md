# UI Design System — Monochrome Bento Glassmorphism (iDraft Reference)

## 1. Visual Direction
- **Aesthetic**: Soft Minimalist Monochrome Bento with Frosted Glassmorphism (inspired by the iDraft reference dashboard).
- **Color Palette**:
  - **Canvas Background**: `#E6E7EB` to `#F0F1F4` with subtle radial monochrome light/shadow gradients.
  - **Outer Glass Shell**: `rgba(255, 255, 255, 0.45)` with `backdrop-filter: blur(24px)` and `1px solid rgba(255, 255, 255, 0.75)`.
  - **Primary Dark Surface**: `#1C1C1F` (Charcoal Jet) with `#FFFFFF` typography and `#2A2A2E` subtle dividers.
  - **Primary Light Surface**: `#FFFFFF` (Pure White) with `#18181B` typography.
  - **Frosted Glass Card**: `rgba(255, 255, 255, 0.62)` with `backdrop-filter: blur(16px)` and `1px solid rgba(255, 255, 255, 0.85)`.
  - **Soft Inner Surface**: `#EBECEE` for nested metric pills inside dark cards.
- **Geometry & Border Radius**:
  - Outer Shell: `36px`
  - Sidebar & Primary Bento Cards: `28px` – `32px`
  - Nested Metric Sub-cards & Task Cards: `22px` – `26px`
  - Buttons & Nav Items: Full pill (`9999px`) or squircle (`16px`).
- **Interactivity & Motion**:
  - Staggered card entrance (`fadeUp`), smooth spring hover lifts (`-translate-y-1`), playful card tilt on in-progress items, interactive SVG line/radial charts, dark floating context menus (`Pin`, `Edit`, `Reminder`, `Archive`), and instant modal transitions.
