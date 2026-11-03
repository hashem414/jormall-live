import type { CSSProperties } from "react";

const hexColorPattern = /^#[0-9a-f]{6}$/iu;

const jormallTheme = {
  accent: "#ff474d",
  primary: "#22b8e6",
} as const;

const beautyCenterTheme = { accent: "#f08aaa", primary: "#9f4f88" } as const;

type RGB = Readonly<{ blue: number; green: number; red: number }>;

export type OrganizationTheme = Readonly<{
  accent: string;
  accentRgb: string;
  accentSoft: string;
  nav: string;
  onPrimary: "#ffffff" | "#102027";
  primary: string;
  primaryRgb: string;
  primarySoft: string;
  primaryStrong: string;
}>;

export type OrganizationThemeStyle = CSSProperties & {
  "--accent": string;
  "--accent-rgb": string;
  "--accent-soft": string;
  "--brand": string;
  "--brand-dark": string;
  "--brand-rgb": string;
  "--brand-soft": string;
  "--nav": string;
  "--on-brand": string;
};

function safeHex(value: string | null | undefined, fallback: string): string {
  const normalized = value?.trim().toLowerCase();
  return normalized && hexColorPattern.test(normalized) ? normalized : fallback;
}

function toRgb(hex: string): RGB {
  return {
    blue: Number.parseInt(hex.slice(5, 7), 16),
    green: Number.parseInt(hex.slice(3, 5), 16),
    red: Number.parseInt(hex.slice(1, 3), 16),
  };
}

function relativeLuminance(hex: string): number {
  const { blue, green, red } = toRgb(hex);
  const linear = (channel: number) => {
    const normalized = channel / 255;
    return normalized <= 0.04045 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
  };
  return linear(red) * 0.2126 + linear(green) * 0.7152 + linear(blue) * 0.0722;
}

export function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(relativeLuminance(foreground), relativeLuminance(background));
  const darker = Math.min(relativeLuminance(foreground), relativeLuminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

function toHex({ blue, green, red }: RGB): string {
  return `#${[red, green, blue]
    .map((channel) => Math.round(channel).toString(16).padStart(2, "0"))
    .join("")}`;
}

function mix(color: string, target: string, targetWeight: number): string {
  const sourceRgb = toRgb(color);
  const targetRgb = toRgb(target);
  const sourceWeight = 1 - targetWeight;
  return toHex({
    blue: sourceRgb.blue * sourceWeight + targetRgb.blue * targetWeight,
    green: sourceRgb.green * sourceWeight + targetRgb.green * targetWeight,
    red: sourceRgb.red * sourceWeight + targetRgb.red * targetWeight,
  });
}

function rgbChannels(hex: string): string {
  const { blue, green, red } = toRgb(hex);
  return `${red} ${green} ${blue}`;
}

function readableText(hex: string): "#ffffff" | "#102027" {
  const { blue, green, red } = toRgb(hex);
  const luminance = (red * 299 + green * 587 + blue * 114) / 1000;
  return luminance < 150 ? "#ffffff" : "#102027";
}

export function createOrganizationTheme(
  input: Readonly<{
    accentColor?: string | null | undefined;
    primaryColor?: string | null | undefined;
  }>,
): OrganizationTheme {
  const fallback = input.primaryColor || input.accentColor ? beautyCenterTheme : jormallTheme;
  const primary = safeHex(input.primaryColor, fallback.primary);
  const accent = safeHex(input.accentColor, fallback.accent);

  return {
    accent,
    accentRgb: rgbChannels(accent),
    accentSoft: mix(accent, "#ffffff", 0.88),
    nav: mix(primary, "#0a1623", 0.82),
    onPrimary: readableText(primary),
    primary,
    primaryRgb: rgbChannels(primary),
    primarySoft: mix(primary, "#ffffff", 0.9),
    primaryStrong: mix(primary, "#0a1623", 0.34),
  };
}

export function organizationThemeStyle(theme: OrganizationTheme): OrganizationThemeStyle {
  return {
    "--accent": theme.accent,
    "--accent-rgb": theme.accentRgb,
    "--accent-soft": theme.accentSoft,
    "--brand": theme.primary,
    "--brand-dark": theme.primaryStrong,
    "--brand-rgb": theme.primaryRgb,
    "--brand-soft": theme.primarySoft,
    "--nav": theme.nav,
    "--on-brand": theme.onPrimary,
  };
}
