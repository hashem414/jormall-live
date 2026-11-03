import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Feedback } from "../../../components/feedback";
import { JorMallBrand } from "../../../components/organization-branding";
import { SubmitButton } from "../../../components/submit-button";
import { phaseOneMessages } from "../../../messages/phase-one";
import { getSession } from "../../../server/session";
import { loginAction } from "../actions";

export default async function LoginPage({ params, searchParams }: PageProps<"/[locale]/login">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) {
    notFound();
  }
  const session = await getSession();
  if (session) {
    redirect(`/${locale}/dashboard`);
  }
  const query = await searchParams;
  const messages = phaseOneMessages[locale];
  const returnTo = typeof query.returnTo === "string" ? query.returnTo : "";
  return (
    <main className="auth-shell login-shell">
      <section aria-label={messages.appName} className="auth-visual">
        <div className="auth-visual-brand">
          <JorMallBrand />
        </div>
        <div className="auth-visual-copy">
          <p className="eyebrow">{messages.appDescription}</p>
          <h2>{messages.loginWelcome}</h2>
          <ul className="auth-feature-list">
            <li>{messages.loginFeatureClear}</li>
            <li>{messages.loginFeatureSecure}</li>
            <li>{messages.loginFeatureBilingual}</li>
          </ul>
        </div>
        <div className="auth-product-preview" aria-hidden="true">
          <span className="auth-preview-topline" />
          <span className="auth-preview-sidebar" />
          <span className="auth-preview-card preview-card-one" />
          <span className="auth-preview-card preview-card-two" />
          <span className="auth-preview-card preview-card-three" />
        </div>
      </section>
      <section aria-labelledby="login-title" className="auth-card login-card">
        <div className="auth-card-brand">
          <JorMallBrand />
        </div>
        <div>
          <p className="eyebrow">{messages.appName}</p>
          <h1 id="login-title">{messages.login}</h1>
          <p className="muted">{messages.appDescription}</p>
        </div>
        <Feedback
          error={typeof query.error === "string" ? query.error : undefined}
          locale={locale}
          notice={typeof query.notice === "string" ? query.notice : undefined}
        />
        <form action={loginAction} className="form-stack">
          <input name="locale" type="hidden" value={locale} />
          <input name="returnTo" type="hidden" value={returnTo} />
          <label className="field">
            <span className="field-label">{messages.email}</span>
            <input
              autoComplete="email"
              className="input"
              dir="ltr"
              name="email"
              required
              type="email"
            />
          </label>
          <label className="field">
            <span className="field-label">{messages.password}</span>
            <input
              autoComplete="current-password"
              className="input"
              dir="ltr"
              maxLength={128}
              name="password"
              required
              type="password"
            />
          </label>
          <SubmitButton>{messages.login}</SubmitButton>
        </form>
        <p className="login-first-access">{messages.loginFirstAccess}</p>
        <Link
          className="locale-link"
          href={`/${locale === "en" ? "ar" : "en"}/login`}
          hrefLang={locale === "en" ? "ar" : "en"}
        >
          <span className={locale === "en" ? "is-active" : undefined}>EN</span>
          <span aria-hidden="true">|</span>
          <span className={locale === "ar" ? "is-active" : undefined}>AR</span>
        </Link>
      </section>
    </main>
  );
}
