export type WorkspaceIconName =
  | "ai"
  | "appointments"
  | "audit"
  | "bell"
  | "branch"
  | "business"
  | "calendar"
  | "chevron"
  | "communications"
  | "customers"
  | "doctors"
  | "home"
  | "inbox"
  | "insights"
  | "inventory"
  | "reports"
  | "resources"
  | "schedule"
  | "search"
  | "services"
  | "sparkles"
  | "settings"
  | "team"
  | "waitlist";

const paths: Readonly<Record<WorkspaceIconName, readonly string[]>> = {
  ai: ["M12 3v3", "M12 18v3", "M3 12h3", "M18 12h3", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"],
  appointments: ["M5 4h14v16H5z", "M8 2v4", "M16 2v4", "M5 9h14", "m9 14 2 2 4-5"],
  audit: ["M5 4h14v16H5z", "M8 8h8", "M8 12h8", "M8 16h5"],
  bell: ["M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9", "M10 21h4"],
  branch: ["M4 20V8l8-5 8 5v12", "M9 20v-6h6v6", "M8 10h.01", "M16 10h.01"],
  business: ["M4 8h16v12H4z", "M8 8V5h8v3", "M4 13h16", "M10 13v2h4v-2"],
  calendar: ["M4 6h16v14H4z", "M8 3v6", "M16 3v6", "M4 10h16"],
  chevron: ["m9 18 6-6-6-6"],
  communications: ["M4 5h16v12H8l-4 4z", "M8 9h8", "M8 13h5"],
  customers: [
    "M16 20v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2",
    "M9.5 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    "M17 11a3 3 0 0 0 0-6",
    "M21 20v-2a4 4 0 0 0-3-3.87",
  ],
  home: ["m3 11 9-8 9 8", "M5 10v10h14V10", "M9 20v-6h6v6"],
  doctors: ["M12 3v6", "M9 6h6", "M6 4h12v7a6 6 0 0 1-12 0Z", "M8 21h8", "M12 17v4"],
  inbox: ["M4 5h16v14H4z", "m4 8 4 4 4-4", "M4 13h4l2 3h4l2-3h4"],
  insights: ["M4 20V10", "M10 20V4", "M16 20v-7", "M22 20H2"],
  inventory: ["m4 7 8-4 8 4-8 4z", "M4 7v10l8 4 8-4V7", "M12 11v10"],
  reports: ["M5 3h14v18H5z", "M9 16v-3", "M12 16V8", "M15 16v-5"],
  resources: ["M4 5h16v14H4z", "M8 9h8", "M8 13h8", "M8 17h5"],
  schedule: ["M4 6h16v14H4z", "M8 3v6", "M16 3v6", "M8 14h4", "M8 17h7"],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z", "m20 20-4-4"],
  services: ["m12 3 2.2 4.5L19 8.2l-3.5 3.4.8 4.8-4.3-2.3-4.3 2.3.8-4.8L5 8.2l4.8-.7z"],
  sparkles: [
    "m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2z",
    "m18 14 .8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z",
  ],
  settings: [
    "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
    "M19 12a7 7 0 0 0-.2-1.7l2-1.5-2-3.4-2.4 1a7 7 0 0 0-3-1.7L13 2h-4l-.4 2.7a7 7 0 0 0-3 1.7l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 3 12c0 .6.1 1.2.2 1.7l-2 1.5 2 3.4 2.4-1a7 7 0 0 0 3 1.7L9 22h4l.4-2.7a7 7 0 0 0 3-1.7l2.4 1 2-3.4-2-1.5c.1-.5.2-1.1.2-1.7Z",
  ],
  team: [
    "M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
    "M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    "M17 11a3 3 0 1 0 0-6",
    "M22 20v-2a4 4 0 0 0-3-3.87",
  ],
  waitlist: [
    "M5 4h14v16H5z",
    "M8 8h8",
    "M8 12h5",
    "M8 16h4",
    "M17 14v5",
    "m14.5 16.5 2.5 2.5 2.5-2.5",
  ],
};

export function WorkspaceIcon({ name }: Readonly<{ name: WorkspaceIconName }>) {
  return (
    <svg aria-hidden="true" fill="none" height="20" viewBox="0 0 24 24" width="20">
      {paths[name].map((path) => (
        <path
          d={path}
          key={path}
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      ))}
    </svg>
  );
}
