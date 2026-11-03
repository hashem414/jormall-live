const fs = require('fs');
const crypto = require('crypto');
const destination = '/opt/jormall/apps/appointments-v2/.env';
if (fs.existsSync(destination)) throw new Error('Refusing to replace existing deployment secrets');
const secret = () => crypto.randomBytes(32).toString('hex');
const postgres = secret();
const redis = secret();
const values = {
  NODE_ENV: 'production',
  NEXT_PUBLIC_APP_URL: 'https://appointments.jormallapp.com',
  OTEL_SERVICE_NAME: 'jormall-appointments-v2-preview',
  POSTGRES_PASSWORD: postgres,
  REDIS_PASSWORD: redis,
  DATABASE_URL: `postgresql://jormall_v2:${postgres}@postgres:5432/jormall_preview`,
  REDIS_URL: `redis://:${redis}@redis:6379/0`,
  AUTH_SECRET: secret(),
  CREDENTIAL_ENCRYPTION_KEY: crypto.randomBytes(32).toString('base64'),
  MOCK_WHATSAPP_WEBHOOK_SECRET: secret(),
  MOCK_VOICE_WEBHOOK_SECRET: secret(),
  WIDGET_SIGNING_SECRET: secret(),
  DEV_SEED_PASSWORD: crypto.randomBytes(18).toString('hex'),
};
fs.writeFileSync(destination, Object.entries(values).map(([k,v]) => `${k}=${v}`).join('\n')+'\n', {mode:0o600, flag:'wx'});
console.log('Created isolated deployment secrets; no credentials printed.');
