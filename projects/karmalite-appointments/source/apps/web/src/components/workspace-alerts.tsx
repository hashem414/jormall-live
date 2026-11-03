"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { WorkspaceIcon } from "./workspace-icon";

const alertsSchema = z.object({
  notifications: z
    .array(
      z.object({
        id: z.uuid(),
        message: z.string(),
        messageAr: z.string(),
        priority: z.enum(["LOW", "NORMAL", "HIGH", "URGENT"]),
        route: z.string(),
        title: z.string(),
        titleAr: z.string(),
      }),
    )
    .default([]),
  unreadCount: z.number().int().nonnegative().default(0),
});

type Notification = z.infer<typeof alertsSchema>["notifications"][number];

export function WorkspaceAlerts({ locale }: Readonly<{ locale: "ar" | "en" }>) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [notifications, setNotifications] = useState<readonly Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/workspace/alerts", { signal: controller.signal })
      .then(async (response) => alertsSchema.safeParse(await response.json()))
      .then((parsed) => {
        if (parsed.success) {
          setNotifications(parsed.data.notifications);
          setUnreadCount(parsed.data.unreadCount);
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  async function openNotification(notification: Notification): Promise<void> {
    const response = await fetch("/api/workspace/alerts", {
      body: JSON.stringify({ id: notification.id }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    });
    if (response.ok) {
      setNotifications((items) => items.filter(({ id }) => id !== notification.id));
      setUnreadCount((value) => Math.max(0, value - 1));
    }
    setOpen(false);
    router.push(`/${locale}${notification.route}`);
  }

  const labels =
    locale === "ar"
      ? {
          alerts: "التنبيهات",
          empty: "لا توجد تنبيهات جديدة.",
          viewAll: "عرض جميع الإشعارات",
        }
      : { alerts: "Alerts", empty: "No new notifications.", viewAll: "View all notifications" };

  return (
    <div className="header-popover alerts-popover" ref={containerRef}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={labels.alerts}
        className="header-popover-trigger"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <WorkspaceIcon name="bell" />
        {unreadCount > 0 ? (
          <span className="alert-count">{unreadCount > 99 ? "99+" : unreadCount}</span>
        ) : null}
      </button>
      {open ? (
        <div aria-label={labels.alerts} className="header-popover-panel" role="dialog">
          <strong>{labels.alerts}</strong>
          {notifications.length > 0 ? (
            <ul className="alert-list">
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button onClick={() => void openNotification(notification)} type="button">
                    <span>
                      <strong>{locale === "ar" ? notification.titleAr : notification.title}</strong>
                      <small>
                        {locale === "ar" ? notification.messageAr : notification.message}
                      </small>
                    </span>
                    <span className="status">{notification.priority}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>{labels.empty}</p>
          )}
          <Link href={`/${locale}/notifications`} onClick={() => setOpen(false)}>
            {labels.viewAll}
          </Link>
        </div>
      ) : null}
    </div>
  );
}
