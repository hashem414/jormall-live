"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { WorkspaceIcon, type WorkspaceIconName } from "./workspace-icon";

export type DashboardNavigationItem = Readonly<{
  activePrefixes?: readonly string[];
  href: string;
  icon: WorkspaceIconName;
  label: string;
  mobileLabel?: string;
}>;

export type DashboardNavigationGroup = Readonly<{
  items: readonly DashboardNavigationItem[];
  label: string;
}>;

type DashboardNavigationProperties = Readonly<{
  ariaLabel: string;
  closeSidebarLabel: string;
  groups: readonly DashboardNavigationGroup[];
  menuLabel: string;
  openSidebarLabel: string;
}>;

function NavigationLink({
  item,
  mobile = false,
}: Readonly<{ item: DashboardNavigationItem; mobile?: boolean }>) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [itemPath, itemQuery] = item.href.split("?");
  const expectedTab = new URLSearchParams(itemQuery).get("tab");
  const isCurrent =
    item.activePrefixes?.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    ) ??
    (expectedTab
      ? pathname === itemPath && searchParams.get("tab") === expectedTab
      : pathname === itemPath || pathname.startsWith(`${itemPath}/`));

  return (
    <Link
      aria-current={isCurrent ? "page" : undefined}
      data-tooltip={item.label}
      href={item.href}
      title={item.label}
    >
      <WorkspaceIcon name={item.icon} />
      <span>{mobile ? (item.mobileLabel ?? item.label) : item.label}</span>
    </Link>
  );
}

export function DashboardNavigation({
  ariaLabel,
  closeSidebarLabel,
  groups,
  menuLabel,
  openSidebarLabel,
}: DashboardNavigationProperties) {
  const [collapsed, setCollapsed] = useState(false);
  const mobileItems = groups
    .flatMap(({ items }) => items)
    .filter(({ icon }) =>
      (
        ["home", "appointments", "waitlist", "customers", "communications", "reports"] as const
      ).includes(
        icon as "appointments" | "communications" | "customers" | "home" | "reports" | "waitlist",
      ),
    )
    .slice(0, 5);

  return (
    <>
      <aside className={`workspace-sidebar${collapsed ? " is-collapsed" : ""}`}>
        <div className="sidebar-rail-header">
          <span>{menuLabel}</span>
          <button
            aria-expanded={!collapsed}
            aria-label={collapsed ? openSidebarLabel : closeSidebarLabel}
            className="sidebar-toggle"
            onClick={() => setCollapsed((value) => !value)}
            type="button"
          >
            <WorkspaceIcon name="chevron" />
          </button>
        </div>
        <nav aria-label={ariaLabel} className="side-nav">
          {groups.map((group) => (
            <section className="nav-group" key={group.label}>
              <h2>{group.label}</h2>
              <div className="nav-links">
                {group.items.map((item) => (
                  <NavigationLink item={item} key={item.href} />
                ))}
              </div>
            </section>
          ))}
        </nav>
      </aside>
      <nav aria-label={menuLabel} className="mobile-bottom-navigation">
        {mobileItems.map((item) => (
          <NavigationLink item={item} key={item.href} mobile />
        ))}
      </nav>
    </>
  );
}
