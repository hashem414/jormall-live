import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import DashboardClient from "../app/dashboard-client";
import LoginClient from "../app/login/login-client";

test("server-renders the bilingual employee login", () => {
  const html = renderToStaticMarkup(<LoginClient />);
  assert.match(html, /تسجيل الدخول/);
  assert.match(html, /manager@nova\.local/);
  assert.match(html, /الوصول مخصص للمدير/);
  assert.doesNotMatch(html, /Nova-Local-Manager/);
  assert.match(html, /Secure sessions|جلسات آمنة/);
});

test("server-renders a role-aware Nova workspace", () => {
  const html = renderToStaticMarkup(
    <DashboardClient
      displayName="Sara Haddad"
      userId="u2"
      accessRole="employee"
      position="Backend Engineer"
    />,
  );
  assert.match(html, /AI Division OS/);
  assert.match(html, /Sara Haddad/);
  assert.match(html, /My Work/);
  assert.doesNotMatch(html, />Team</);
});
