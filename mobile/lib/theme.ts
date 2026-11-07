// ARTHUR interface theme — muse.ai web dark aesthetic:
// near-black canvas, subtle dark cards, Meta blue accent.

export const theme = {
  colors: {
    background: "#1A1A1E",
    surface: "#26262A",
    surfaceAlt: "#2E2E32",
    border: "#2E2E32",
    primary: "#0082FB",
    primaryDim: "#0F2B4A",
    primaryDark: "#5B9BFF",
    accent: "#7A5AF8",
    success: "#31A24C",
    warning: "#D9A13B",
    danger: "#E06C5B",
    text: "#EDEDED",
    textDim: "#A8A8AD",
    textFaint: "#6E6E73",
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
  },
  radius: {
    sm: 8,
    md: 14,
    lg: 20,
    xl: 28,
  },
} as const;

export type Theme = typeof theme;
