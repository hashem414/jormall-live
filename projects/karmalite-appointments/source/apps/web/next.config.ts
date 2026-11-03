import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["192.168.0.6"],
  experimental: { serverActions: { bodySizeLimit: "6mb" } },
  output: "standalone",
  outputFileTracingIncludes: { "/api/workspace/logo": ["../../Karmalite Logo.png"] },
  outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url)),
  poweredByHeader: false,
  reactStrictMode: true,
  async redirects() {
    return [
      {
        destination: "/en",
        permanent: false,
        source: "/",
      },
      {
        destination: "/:locale/schedule/today",
        permanent: false,
        source: "/:locale/dashboard/today",
      },
      {
        destination: "/:locale/schedule/calendar",
        permanent: false,
        source: "/:locale/dashboard/calendar",
      },
      {
        destination: "/:locale/schedule/waitlist",
        permanent: false,
        source: "/:locale/dashboard/waitlist",
      },
      {
        destination: "/:locale/schedule/appointments?appointment=:appointmentId",
        permanent: false,
        source: "/:locale/dashboard/appointments/:appointmentId",
      },
      {
        destination: "/:locale/customers",
        permanent: false,
        source: "/:locale/dashboard/customers",
      },
      {
        destination: "/:locale/customers/:customerId",
        permanent: false,
        source: "/:locale/dashboard/customers/:customerId",
      },
      {
        destination: "/:locale/inbox?tab=messages",
        permanent: false,
        source: "/:locale/dashboard/communications",
      },
      {
        destination: "/:locale/inbox?tab=conversations",
        permanent: false,
        source: "/:locale/dashboard/ai-conversations",
      },
      {
        destination: "/:locale/inbox?tab=handoffs",
        permanent: false,
        source: "/:locale/dashboard/ai-handoffs",
      },
      {
        destination: "/:locale/business/services",
        permanent: false,
        source: "/:locale/dashboard/services",
      },
      {
        destination: "/:locale/business/team?tab=team",
        permanent: false,
        source: "/:locale/dashboard/staff",
      },
      {
        destination: "/:locale/business/team?tab=roles",
        permanent: false,
        source: "/:locale/dashboard/roles",
      },
      {
        destination: "/:locale/business/resources",
        permanent: false,
        source: "/:locale/dashboard/resources",
      },
      {
        destination: "/:locale/business/branches",
        permanent: false,
        source: "/:locale/dashboard/branches",
      },
      {
        destination: "/:locale/insights/reports",
        permanent: false,
        source: "/:locale/dashboard/reports",
      },
      {
        destination: "/:locale/insights/recommendations?view=copilot",
        permanent: false,
        source: "/:locale/dashboard/copilot",
      },
      {
        destination: "/:locale/insights/recommendations?view=predictions",
        permanent: false,
        source: "/:locale/dashboard/predictions",
      },
      {
        destination: "/:locale/ai-studio/knowledge",
        permanent: false,
        source: "/:locale/dashboard/knowledge",
      },
      {
        destination: "/:locale/ai-studio/behavior",
        permanent: false,
        source: "/:locale/dashboard/ai-settings",
      },
      {
        destination: "/:locale/ai-studio/actions",
        permanent: false,
        source: "/:locale/dashboard/ai-actions",
      },
      {
        destination: "/:locale/ai-studio/usage",
        permanent: false,
        source: "/:locale/dashboard/ai-usage",
      },
      {
        destination: "/:locale/settings/channels",
        permanent: false,
        source: "/:locale/dashboard/ai-channels",
      },
      {
        destination: "/:locale/settings/organization",
        permanent: false,
        source: "/:locale/dashboard/settings",
      },
      {
        destination: "/:locale/settings/imports",
        permanent: false,
        source: "/:locale/dashboard/imports",
      },
      {
        destination: "/:locale/settings/audit",
        permanent: false,
        source: "/:locale/dashboard/audit",
      },
    ];
  },
  transpilePackages: [
    "@jormall/ai",
    "@jormall/auth",
    "@jormall/contracts",
    "@jormall/db",
    "@jormall/domain",
    "@jormall/ui",
  ],
};

export default nextConfig;
