import { ResourceKind } from "@jormall/db/generated/enums";

export const beautyResourceKinds = [
  ResourceKind.ROOM,
  ResourceKind.CHAIR,
  ResourceKind.DEVICE,
  ResourceKind.SHARED_EQUIPMENT,
] as const;
