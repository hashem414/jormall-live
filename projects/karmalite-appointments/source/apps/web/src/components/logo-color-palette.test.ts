import { describe, expect, it } from "vitest";

import { extractLogoPalette } from "./logo-color-palette";

function pixels(
  ...colors: ReadonlyArray<readonly [number, number, number, number]>
): Uint8ClampedArray {
  return new Uint8ClampedArray(colors.flat());
}

describe("extractLogoPalette", () => {
  it("extracts the dominant saturated logo color and a distinct accent", () => {
    const palette = extractLogoPalette(
      pixels(
        [24, 144, 112, 255],
        [24, 144, 112, 255],
        [24, 144, 112, 255],
        [245, 165, 36, 255],
        [245, 165, 36, 255],
      ),
    );

    expect(palette).toMatchObject({ accent: "#f5a524", primary: "#189070" });
  });

  it("ignores transparent, white and near-gray background pixels", () => {
    const palette = extractLogoPalette(
      pixels([255, 255, 255, 255], [220, 220, 220, 255], [34, 184, 230, 255], [255, 71, 77, 0]),
    );

    expect(palette?.primary).toBe("#22b8e6");
    expect(palette?.colors).toHaveLength(1);
  });
});
