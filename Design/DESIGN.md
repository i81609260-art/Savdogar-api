---
name: Indigo Glass Tech-Forward
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#464555'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#6b38d4'
  on-secondary: '#ffffff'
  secondary-container: '#8455ef'
  on-secondary-container: '#fffbff'
  tertiary: '#005338'
  on-tertiary: '#ffffff'
  tertiary-container: '#006e4b'
  on-tertiary-container: '#67f4b7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Outfit
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
  headline-lg:
    fontFamily: Outfit
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-md:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style
The brand personality is tech-forward, premium, and highly efficient, designed to inspire confidence in travel operators and CRM power users. The visual identity balances a serious enterprise tool with the aspirational nature of the travel industry.

The design system employs **Fluent Glassmorphism** as its core aesthetic. This involves the use of frosted glass surfaces, multi-layered transparency, and vibrant background blurs that create a sense of depth and modernity. The style is characterized by high-fidelity micro-interactions, precision-engineered layouts, and a "living" UI that feels reactive and immersive rather than static and flat.

## Colors
The palette is anchored by a deep, high-energy Indigo, symbolizing reliability and technological depth. Violet serves as a vibrant secondary accent to drive action and highlight premium features, while Mint provides a crisp, legible status for success states and financial confirmations.

The background uses a subtle, cool-toned off-white in light mode to maintain high legibility for data-heavy CRM tables. In dark mode, a deep navy-slate provides the necessary contrast for glass effects to glow. Use semi-transparent variants of these colors (Alpha 10-20%) for glass borders and surface overlays to maintain the glassmorphic theme.

## Typography
The typography system uses a dual-font approach to differentiate between brand expression and functional data management. 

**Outfit** is used for all headlines and display text. Its geometric construction and modern feel align with the tech-forward brand DNA. **Inter** is the workhorse for body text, CRM data, and labels, chosen for its exceptional legibility at small sizes and its neutral, systematic character. For large data visualizations or dashboard metrics, use `headline-md` with Inter to ensure clarity.

## Layout & Spacing
This design system utilizes a **Fluid Grid** model based on a 12-column system for desktop and a 4-column system for mobile. Layouts are built on an 8px base grid to ensure vertical rhythm and consistent alignment across complex CRM modules.

- **Desktop (1440px+):** 12 columns, 24px gutters, 40px outer margins.
- **Tablet (768px - 1439px):** 8 columns, 20px gutters, 24px outer margins.
- **Mobile (<767px):** 4 columns, 16px gutters, 16px outer margins.

Spacing between functional groups should use `md` (24px), while internal component padding should stick to the `sm` (12px) or `xs` (4px) increments. Dashboard widgets should use `lg` (48px) spacing to prevent visual clutter in data-dense views.

## Elevation & Depth
Depth is created through light and transparency rather than heavy shadows. The primary elevation tool is the **Glassmorphism Backdrop**.

1.  **Level 0 (Base):** Solid background color (Light or Dark).
2.  **Level 1 (Cards/Panels):** `backdrop-filter: blur(12px)`, background opacity at 60-70%, and a 1px solid border at 10% white (light mode) or 10% indigo (dark mode).
3.  **Level 2 (Modals/Popovers):** Higher blur (`24px`), background opacity at 80%, and a subtle 20px ambient shadow with a tint of the Primary Indigo color at 5% opacity.

All glass surfaces should feature a subtle "inner glow" achieved by a 1px top-border that is slightly lighter than the rest of the stroke to simulate light hitting the edge of the glass.

## Shapes
The shape language is "Rounded," utilizing a 0.5rem (8px) corner radius for standard components like input fields and small buttons. This provides a approachable yet professional look.

- **Cards & Dashboard Widgets:** Use `rounded-lg` (16px) to define distinct sections within the fluid layout.
- **Large Container Surfacing:** Use `rounded-xl` (24px) for main content areas or modal overlays.
- **Pill Shapes:** Apply to Chips, Tags, and Status Indicators to distinguish them from interactive action buttons.

## Components
- **Buttons:** Primary buttons must use a linear gradient from Primary Indigo to Secondary Violet (45-degree angle). They feature a `scale: 1.02` hover effect and a `translateY(-2px)` transition. Secondary buttons are "ghost" glass style with a 1px Indigo border.
- **Cards:** All cards utilize the Level 1 glass elevation. On hover, the background opacity should increase by 10%, and the border should brighten.
- **Inputs:** Fields are semi-transparent with a 1px bottom-heavy border. On focus, the border transitions to a solid 2px Primary Indigo with a soft 4px outer glow.
- **Chips:** Small, pill-shaped elements with low-opacity backgrounds (10%) matching their semantic meaning (e.g., Mint for "Paid," Indigo for "Pending").
- **Lists:** CRM list items should have a subtle separator line (5% opacity neutral) and a hover state that applies a very light Indigo glass tint to the entire row.
- **Micro-interactions:** Use `cubic-bezier(0.34, 1.56, 0.64, 1)` for all transitions to give a "snappy" and high-tech feel to scales and movements.