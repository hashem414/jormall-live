type PaletteColor = Readonly<{
  blue: number;
  count: number;
  green: number;
  red: number;
  saturation: number;
}>;

export type ExtractedLogoPalette = Readonly<{
  accent: string;
  colors: readonly string[];
  primary: string;
}>;

function channelHex(channel: number): string {
  return Math.max(0, Math.min(255, Math.round(channel)))
    .toString(16)
    .padStart(2, "0");
}

function toHex(color: PaletteColor): string {
  return `#${channelHex(color.red)}${channelHex(color.green)}${channelHex(color.blue)}`;
}

function colorDistance(left: PaletteColor, right: PaletteColor): number {
  return Math.hypot(left.red - right.red, left.green - right.green, left.blue - right.blue);
}

function quantize(channel: number): number {
  return Math.min(255, Math.round(channel / 24) * 24);
}

export function extractLogoPalette(pixelData: Uint8ClampedArray): ExtractedLogoPalette | null {
  const buckets = new Map<string, PaletteColor>();

  for (let index = 0; index + 3 < pixelData.length; index += 4) {
    const red = pixelData.at(index) ?? 0;
    const green = pixelData.at(index + 1) ?? 0;
    const blue = pixelData.at(index + 2) ?? 0;
    const alpha = pixelData.at(index + 3) ?? 0;
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const chroma = maximum - minimum;

    if (alpha < 180 || minimum > 246 || maximum < 14 || chroma < 16) continue;

    const key = `${quantize(red)}-${quantize(green)}-${quantize(blue)}`;
    const existing = buckets.get(key);
    const count = (existing?.count ?? 0) + 1;
    const saturation = maximum === 0 ? 0 : chroma / maximum;
    buckets.set(key, {
      blue: ((existing?.blue ?? 0) * (count - 1) + blue) / count,
      count,
      green: ((existing?.green ?? 0) * (count - 1) + green) / count,
      red: ((existing?.red ?? 0) * (count - 1) + red) / count,
      saturation: Math.max(existing?.saturation ?? 0, saturation),
    });
  }

  const ranked = Array.from(buckets.values()).sort(
    (left, right) => right.count * (0.7 + right.saturation) - left.count * (0.7 + left.saturation),
  );
  const primary = ranked.at(0);
  if (!primary) return null;

  const accent =
    ranked
      .slice(1)
      .filter((candidate) => colorDistance(primary, candidate) >= 60)
      .sort(
        (left, right) =>
          right.count * right.saturation * colorDistance(primary, right) -
          left.count * left.saturation * colorDistance(primary, left),
      )
      .at(0) ??
    ranked.at(1) ??
    primary;

  const distinctColors: PaletteColor[] = [];
  for (const candidate of ranked) {
    if (distinctColors.every((color) => colorDistance(color, candidate) >= 36)) {
      distinctColors.push(candidate);
    }
    if (distinctColors.length === 5) break;
  }

  return {
    accent: toHex(accent),
    colors: distinctColors.map(toHex),
    primary: toHex(primary),
  };
}
