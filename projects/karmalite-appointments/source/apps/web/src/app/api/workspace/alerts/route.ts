import { operationalWorkflowsRepository } from "../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../server/workspace-http";

export async function GET(): Promise<Response> {
  try {
    const access = await requireApiTenantAccess();
    const [notifications, unreadCount] = await Promise.all([
      operationalWorkflowsRepository.listNotifications(access, "UNREAD", 8),
      operationalWorkflowsRepository.countUnreadNotifications(access),
    ]);
    return workspaceJson({
      notifications: notifications.map((notification) => ({
        id: notification.id,
        message: notification.messageEn,
        messageAr: notification.messageAr,
        priority: notification.priority,
        route: notification.targetRoute,
        title: notification.titleEn,
        titleAr: notification.titleAr,
      })),
      unreadCount,
    });
  } catch (error) {
    return workspaceError(error);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    const body: unknown = await request.json();
    if (typeof body !== "object" || body === null || !("id" in body) || typeof body.id !== "string")
      return workspaceJson({ code: "VALIDATION_FAILED" }, 400);
    const access = await requireApiTenantAccess();
    await operationalWorkflowsRepository.setNotificationState(access, {
      id: body.id,
      state: "READ",
    });
    return workspaceJson({ ok: true });
  } catch (error) {
    return workspaceError(error);
  }
}
