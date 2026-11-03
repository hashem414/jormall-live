"use client";

import { useState } from "react";

import { extractLogoPalette } from "./logo-color-palette";
import { OrganizationLogo } from "./organization-branding";
import {
  contrastRatio,
  createOrganizationTheme,
  organizationThemeStyle,
} from "./organization-theme";

type BrandingMessages = Readonly<{
  accentColor: string;
  colorExtractionFailed: string;
  colorHint: string;
  colorsExtracted: string;
  extractColors: string;
  extractingColors: string;
  logoFile: string;
  logoFileHint: string;
  logoUrl: string;
  logoUrlHint: string;
  palette: string;
  preview: string;
  primaryColor: string;
  saveChanges: string;
}>;

type ExtractionStatus = "extracted" | "extracting" | "failed" | "idle";

async function readPaletteFromImage(source: string, useCrossOrigin: boolean) {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const element = new Image();
    if (useCrossOrigin) element.crossOrigin = "anonymous";
    element.decoding = "async";
    element.onload = () => resolve(element);
    element.onerror = () => reject(new Error("LOGO_IMAGE_LOAD_FAILED"));
    element.src = source;
  });
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 96;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("LOGO_CANVAS_UNAVAILABLE");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return extractLogoPalette(context.getImageData(0, 0, canvas.width, canvas.height).data);
}

export function OrganizationBrandingFields({
  accentColor: initialAccentColor,
  logoUrl: initialLogoUrl,
  messages,
  locale,
  organizationName,
  primaryColor: initialPrimaryColor,
}: Readonly<{
  accentColor: string;
  logoUrl: string | null;
  messages: BrandingMessages;
  locale: "ar" | "en";
  organizationName: string;
  primaryColor: string;
}>) {
  const [accentColor, setAccentColor] = useState(initialAccentColor);
  const [extractionStatus, setExtractionStatus] = useState<ExtractionStatus>("idle");
  const [logoUrl, setLogoUrl] = useState(initialLogoUrl ?? "");
  const [primaryColor, setPrimaryColor] = useState(initialPrimaryColor);
  const theme = createOrganizationTheme({ accentColor, primaryColor });
  const primaryContrast = contrastRatio(theme.onPrimary, theme.primary);
  const contrastPasses = primaryContrast >= 4.5;
  const paletteSwatches = [
    theme.primary,
    theme.accent,
    theme.primaryStrong,
    theme.primarySoft,
    theme.accentSoft,
  ].filter((color, index, colors) => colors.indexOf(color) === index);

  async function applyExtractedPalette(source: string, useCrossOrigin: boolean) {
    setExtractionStatus("extracting");
    try {
      const palette = await readPaletteFromImage(source, useCrossOrigin);
      if (!palette) throw new Error("LOGO_COLORS_NOT_FOUND");
      setPrimaryColor(palette.primary);
      setAccentColor(palette.accent);
      setExtractionStatus("extracted");
    } catch {
      setExtractionStatus("failed");
    }
  }

  async function extractFromLogoUrl() {
    try {
      const parsed = new URL(logoUrl, window.location.origin);
      const isWorkspaceLogo =
        parsed.origin === window.location.origin && parsed.pathname === "/api/workspace/logo";
      if (!isWorkspaceLogo && parsed.protocol !== "https:") throw new Error("LOGO_URL_NOT_SECURE");
      await applyExtractedPalette(parsed.toString(), parsed.origin !== window.location.origin);
    } catch {
      setExtractionStatus("failed");
    }
  }

  async function extractFromLocalFile(file: File) {
    const objectUrl = URL.createObjectURL(file);
    try {
      await applyExtractedPalette(objectUrl, false);
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  const extractionMessage =
    extractionStatus === "extracting"
      ? messages.extractingColors
      : extractionStatus === "extracted"
        ? messages.colorsExtracted
        : extractionStatus === "failed"
          ? messages.colorExtractionFailed
          : null;

  return (
    <div className="branding-editor">
      <div className="branding-fields">
        <div className="field branding-logo-field">
          <label className="field-label" htmlFor="brandLogoUrl">
            {messages.logoUrl}
          </label>
          <span className="branding-logo-url-row">
            <input
              className="input"
              dir="ltr"
              id="brandLogoUrl"
              maxLength={2048}
              name="brandLogoUrl"
              onBlur={(event) => {
                if (
                  event.relatedTarget instanceof HTMLElement &&
                  event.relatedTarget.id === "extractLogoColors"
                ) {
                  return;
                }
                if (logoUrl && logoUrl !== (initialLogoUrl ?? "")) void extractFromLogoUrl();
              }}
              onChange={(event) => {
                setLogoUrl(event.target.value);
                setExtractionStatus("idle");
              }}
              inputMode="url"
              placeholder="https://example.com/logo.png"
              type="text"
              value={logoUrl}
            />
            <button
              className="button button-secondary palette-extract-button"
              disabled={!logoUrl || extractionStatus === "extracting"}
              id="extractLogoColors"
              onClick={() => void extractFromLogoUrl()}
              type="button"
            >
              {messages.extractColors}
            </button>
          </span>
          <small className="field-hint">{messages.logoUrlHint}</small>
        </div>
        <label className="field branding-logo-file-field">
          <span className="field-label">{messages.logoFile}</span>
          <input
            accept="image/png,image/jpeg,image/webp"
            className="input"
            onChange={(event) => {
              const file = event.target.files?.item(0);
              if (file) void extractFromLocalFile(file);
            }}
            type="file"
          />
          <small className="field-hint">{messages.logoFileHint}</small>
        </label>
        {extractionMessage ? (
          <p
            className={`palette-extraction-status is-${extractionStatus}`}
            role={extractionStatus === "failed" ? "alert" : "status"}
          >
            {extractionMessage}
          </p>
        ) : null}
        <div className="branding-color-grid">
          <label className="field color-field">
            <span className="field-label">{messages.primaryColor}</span>
            <span className="color-control">
              <input
                aria-label={messages.primaryColor}
                name="brandPrimaryColor"
                onChange={(event) => setPrimaryColor(event.target.value)}
                type="color"
                value={primaryColor}
              />
              <output dir="ltr">{primaryColor.toUpperCase()}</output>
            </span>
          </label>
          <label className="field color-field">
            <span className="field-label">{messages.accentColor}</span>
            <span className="color-control">
              <input
                aria-label={messages.accentColor}
                name="brandAccentColor"
                onChange={(event) => setAccentColor(event.target.value)}
                type="color"
                value={accentColor}
              />
              <output dir="ltr">{accentColor.toUpperCase()}</output>
            </span>
          </label>
        </div>
        <section className="extracted-palette" aria-label={messages.palette}>
          <strong>{messages.palette}</strong>
          <div className="palette-swatches">
            {paletteSwatches.map((color) => (
              <span key={color} style={{ backgroundColor: color }}>
                <span className="sr-only">{color}</span>
              </span>
            ))}
          </div>
        </section>
        <div className="form-actions">
          <button
            className="button button-secondary"
            onClick={() => {
              setPrimaryColor(initialPrimaryColor);
              setAccentColor(initialAccentColor);
              setExtractionStatus("idle");
            }}
            type="button"
          >
            {locale === "ar" ? "إعادة الألوان الافتراضية" : "Reset default colors"}
          </button>
        </div>
        <p className={contrastPasses ? "status" : "feedback feedback-error"} role="status">
          {locale === "ar" ? "تباين النص مع اللون الأساسي" : "Text contrast on primary"}:{" "}
          {primaryContrast.toFixed(2)}:1 ·{" "}
          {contrastPasses
            ? locale === "ar"
              ? "مطابق لمعيار WCAG AA"
              : "WCAG AA pass"
            : locale === "ar"
              ? "اختر لوناً أكثر تبايناً"
              : "Choose a higher-contrast color"}
        </p>
        <small className="field-hint branding-color-hint">{messages.colorHint}</small>
        <div className="form-actions branding-save-actions">
          <button className="button button-primary" disabled={!contrastPasses} type="submit">
            {messages.saveChanges}
          </button>
        </div>
      </div>

      <aside className="brand-preview-card" style={organizationThemeStyle(theme)}>
        <span className="brand-preview-label">{messages.preview}</span>
        <div className="brand-preview-lockup">
          <OrganizationLogo logoUrl={logoUrl} name={organizationName} />
          <span>
            <strong>{organizationName}</strong>
            <small>{messages.palette}</small>
          </span>
        </div>
        <span className="brand-preview-action">Aa</span>
        <span className="brand-preview-accent" aria-hidden="true" />
        <div className="brand-language-previews">
          <span dir="ltr">EN · Calendar · Customers · Services</span>
          <span dir="rtl">AR · التقويم · العملاء · الخدمات</span>
        </div>
      </aside>
    </div>
  );
}
