# Appointments v2 preview deployment

This is the greenfield JorMall project, running an isolated preview database with
reserved `.invalid` demonstration identities. Provider integrations are mock-only.
The previous application and database are retained and are not imported or reused.

- Public URL: https://appointments.jormallapp.com
- Deployment directory: /opt/jormall/apps/appointments-v2
- Internal HTTP endpoint: 127.0.0.1:18200
- Compose project: jormall-appointments-v2
- Image: jormall-appointments-v2:20260906-slim
- Database and Redis have no host port bindings.
- Credentials are generated on the server in the root-owned, mode-0600 `.env`.
- Containers restart automatically and use bounded memory and rotating logs.

Run `sudo docker compose ps` or `sudo docker compose logs --tail=100` from the
deployment directory for status. The worker uses the same application image.
Its working directory is `/worker/apps/worker`; dependencies were copied from
the exact frozen-lockfile build, without resolving new package versions.
Migrations were run from the source workspace through a localhost-only SSH
database tunnel. The initial seed runs on the server from a bundle of the exact
validated source and locked dependencies. The runtime image excludes build tools.

The one-time seed is only for this fresh preview database, before it is publicly
routed, with development mode confined to the seed process. The public web and
worker always run with NODE_ENV=production and HTTPS secure cookies.

Rollback: start the retained `jormall-appointments-web` container if it has been
stopped, restore the saved Nginx appointments virtual host from
`/home/ubuntu/jormall-deploy-20260906/nginx-before-contents.conf`, run `sudo nginx -t`, and
reload Nginx. Do not delete either database volume during a rollback.
