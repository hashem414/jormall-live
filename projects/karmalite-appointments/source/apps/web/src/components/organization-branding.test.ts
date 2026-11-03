import { describe, expect, it } from "vitest";

import {
  contrastRatio,
  createOrganizationTheme,
  organizationThemeStyle,
} from "./organization-theme";

describe("organization branding", () => {
  it("uses validated organization colors as workspace CSS variables", () => {
    const theme = createOrganizationTheme({
      accentColor: "#F04F59",
      primaryColor: "#126D82",
    });

    expect(theme).toMatchObject({
      accent: "#f04f59",
      onPrimary: "#ffffff",
      primary: "#126d82",
    });
    expect(organizationThemeStyle(theme)).toMatchObject({
      "--accent": "#f04f59",
      "--brand": "#126d82",
      "--brand-rgb": "18 109 130",
    });
  });

  it("falls back to the beauty-center palette when stored colors are malformed", () => {
    const theme = createOrganizationTheme({
      accentColor: "not-a-color",
      primaryColor: "#fff",
    });

    expect(theme.primary).toBe("#9f4f88");
    expect(theme.accent).toBe("#f08aaa");
  });

  it("chooses dark text when a primary color is light", () => {
    expect(createOrganizationTheme({ primaryColor: "#f7d66f" }).onPrimary).toBe("#102027");
  });

  it("calculates WCAG contrast ratios for branding previews", () => {
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  });
});
