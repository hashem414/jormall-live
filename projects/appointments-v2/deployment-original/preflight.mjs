const origin = process.env.NEXT_PUBLIC_APP_URL;
const endpoint = process.argv[2] || 'http://127.0.0.1:3000';
const requestHeaders = {origin, 'x-forwarded-proto': 'https', 'x-forwarded-host': new URL(origin).host, host: new URL(origin).host};
const loginPage = await fetch(`${endpoint}/ar/login`, {headers: requestHeaders});
if (loginPage.status !== 200) throw new Error('Login form is unavailable');
const formHtml = await loginPage.text();
const actionName = formHtml.match(/name="(\$ACTION_ID_[^"]+)"/)?.[1];
if (!actionName) throw new Error('Login server action was not present in the form');
const form = new FormData();
form.set(actionName, '');
form.set('locale', 'ar');
form.set('returnTo', '');
form.set('email', 'owner@example.invalid');
form.set('password', process.env.DEV_SEED_PASSWORD);
const login = await fetch(`${endpoint}/ar/login`, {
  method: 'POST',
  headers: requestHeaders,
  body: form,
  redirect: 'manual',
});
if (login.status !== 303 || !login.headers.get('location')?.endsWith('/ar/dashboard')) {
  throw new Error(`Form sign-in failed with HTTP ${login.status}, location ${login.headers.get('location')}`);
}
const cookies = login.headers.getSetCookie();
if (!cookies.some(value => value.includes('Secure') && value.includes('HttpOnly'))) {
  throw new Error('Expected secure, HTTP-only production session cookie');
}
const cookie = cookies.map(value => value.split(';')[0]).join('; ');
for (const route of ['/ar/dashboard','/ar/schedule/today','/ar/customers','/en/dashboard']) {
  const response = await fetch(`${endpoint}${route}`, {headers: {cookie, host:new URL(origin).host, 'x-forwarded-proto':'https'},redirect:'manual'});
  if (response.status !== 200) throw new Error(`${route} returned HTTP ${response.status}`);
  const html = await response.text();
  if (html.includes('Application error:') || html.includes('Internal Server Error')) throw new Error(`Application error on ${route}`);
  console.log(`${route}: HTTP 200`);
}
console.log('Authenticated preflight passed; production cookies are Secure and HttpOnly.');
