"use client";

import { FormEvent, useState } from "react";
import {
  ArrowRight,
  Languages,
  LockKeyhole,
  Sparkles,
  Users,
} from "lucide-react";

export default function LoginClient() {
  const [locale, setLocale] = useState<"ar" | "en">("ar");
  const [email, setEmail] = useState("manager@nova.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message);
      window.location.assign("/");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : locale === "ar"
            ? "تعذر تسجيل الدخول."
            : "Sign-in failed.",
      );
      setWorking(false);
    }
  };

  return (
    <main
      className="login-page"
      dir={locale === "ar" ? "rtl" : "ltr"}
      lang={locale}
    >
      <section className="login-story">
        <div className="login-brand">
          <span className="brand-mark">
            <Sparkles size={19} />
          </span>
          <span>
            <b>NOVA</b>
            <small>AI DIVISION OS</small>
          </span>
        </div>
        <div>
          <span className="login-kicker">
            <Users size={15} />{" "}
            {locale === "ar"
              ? "مساحة عمل لكل الفريق"
              : "ONE WORKSPACE FOR THE TEAM"}
          </span>
          <h1>
            {locale === "ar"
              ? "كل موظف يدخل إلى يومه، وليس إلى لوحة عامة."
              : "Every teammate signs into their own day—not a generic dashboard."}
          </h1>
          <p>
            {locale === "ar"
              ? "مهامك ومشاريعك وجدولك اليومي بسعة قصوى 8 ساعات، مع صلاحيات منفصلة للمدير والموظف والمشاهد."
              : "Your tasks, projects and daily plan—capped at eight focused hours—with separate manager, employee and viewer access."}
          </p>
        </div>
        <footer>
          <LockKeyhole size={15} />{" "}
          {locale === "ar"
            ? "جلسات آمنة وكلمات مرور مشفّرة"
            : "Secure sessions and hashed passwords"}
        </footer>
      </section>
      <section className="login-workspace">
        <button
          className="login-language"
          type="button"
          onClick={() => setLocale(locale === "ar" ? "en" : "ar")}
        >
          <Languages size={16} /> {locale === "ar" ? "English" : "العربية"}
        </button>
        <form className="login-card" onSubmit={submit}>
          <span className="login-icon">
            <LockKeyhole size={21} />
          </span>
          <h2>{locale === "ar" ? "تسجيل الدخول" : "Sign in"}</h2>
          <p>
            {locale === "ar"
              ? "أدخل بيانات حساب مدير نوفا."
              : "Enter the Nova manager account credentials."}
          </p>
          <label>
            {locale === "ar" ? "البريد الوظيفي" : "Work email"}
            <input
              required
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            {locale === "ar" ? "كلمة المرور" : "Password"}
            <input
              required
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button className="login-submit" disabled={working}>
            {working
              ? locale === "ar"
                ? "جارٍ الدخول…"
                : "Signing in…"
              : locale === "ar"
                ? "دخول إلى نوفا"
                : "Enter Nova"}
            <ArrowRight size={17} />
          </button>
          <small className="demo-note">
            {locale === "ar"
              ? "الوصول مخصص للمدير. يمكنه إنشاء حسابات الموظفين من داخل النظام."
              : "Manager-only access. The manager can create employee accounts inside Nova."}
          </small>
        </form>
      </section>
    </main>
  );
}
