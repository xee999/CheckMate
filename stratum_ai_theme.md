# Stratum AI — Design System & Visual Theme Specification

## 1. Theme Overview
A highly modern, premium, and minimalist UI design system suitable for a futuristic FinTech or AI dashboard. The aesthetic feels airy, organized, and sophisticated, relying on ample whitespace, rounded geometry, and a high-contrast color palette featuring a striking neon lime accent against soft backgrounds and deep dark panels.

---

## 2. Color Palette
- **Primary Accent (Vibrant)**: `#CCF458` (Neon Lime Green) — Active states, key metrics, primary buttons, and chart highlights.
- **Secondary Accent (Deep)**: `#34970D` (Forest Green) — Secondary data points, success states, or gradient transitions.
- **Primary Text & Dark Surfaces**: `#0B090A` (Deepest Charcoal/Almost Black) — Primary headings, dark mode dashboard sections, and high-contrast text.
- **Light Surfaces & Text**: `#FFFFFF` (Pure White) — Cards, widgets, light mode text, and floating elements.
- **Global Background**: `#F1F4EE` (Soft desaturated sage/off-white) allowing white cards to gently pop.
- **Utility / Inactive**: `#E0E5DC` / `#718096` — Soft grays and translucent whites for borders and disabled text.

---

## 3. Typography
- **Primary Font Family**: `'Outfit'`, `'Inter'`, sans-serif.
- **Weights Used**:
  - `Light (300)`: Large data numbers and soft subtitles.
  - `Regular (400)`: Body text and labels.
  - `Medium / Bold (600 - 800)`: Headings and active UI elements.
- **Styling**: Slightly tight letter-spacing for headings; high-contrast metric sizing.

---

## 4. UI Elements & Components
- **Cards & Widgets**: Pure white (`#FFFFFF`) or deep charcoal (`#0B090A`) backgrounds with generous border radiuses (`16px` to `24px`) and subtle soft shadows (`0 8px 30px rgba(11, 9, 10, 0.05)`).
- **Buttons & Tags**: Extreme pill-shaped radiuses (`9999px`). Primary buttons use `#CCF458` Neon Lime with `#0B090A` text.
- **Upload Dropzones**: Styled with `#0B090A` or `#CCF458` accents, custom CSS overriding Quasar default primary blue, soft dashed border (`#E0E5DC`), and pure white background.
- **Badges / Pills**: Floating pills for percentage changes and status indicators (`#CCF458` lime or `#34970D` forest green).
- **Navigation**: Clean, horizontal pill-shaped segmented controls.
