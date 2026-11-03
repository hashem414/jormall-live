import { ResourceKind } from "@jormall/db/generated/enums";
import { describe, expect, it } from "vitest";

import { beautyResourceKinds } from "./beauty-resource-kinds";

describe("beauty-center resource kinds", () => {
  it("exposes only treatment rooms, chairs, machines, and equipment", () => {
    expect(beautyResourceKinds).toEqual([
      ResourceKind.ROOM,
      ResourceKind.CHAIR,
      ResourceKind.DEVICE,
      ResourceKind.SHARED_EQUIPMENT,
    ]);
    expect(beautyResourceKinds).not.toContain(ResourceKind.PROVIDER);
    expect(beautyResourceKinds).not.toContain(ResourceKind.VEHICLE);
    expect(beautyResourceKinds).not.toContain(ResourceKind.OTHER);
  });
});
