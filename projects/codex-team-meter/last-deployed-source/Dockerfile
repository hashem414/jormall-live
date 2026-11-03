FROM node:24-bookworm-slim
WORKDIR /app
COPY --chown=node:node package.json ./
COPY --chown=node:node server ./server
COPY --chown=node:node public ./public
COPY --chown=node:node skills/team-usage-meter/scripts/parser.mjs ./skills/team-usage-meter/scripts/parser.mjs
RUN mkdir -p /app/data && chown node:node /app/data
USER node
ENV PORT=8790 DATA_DIR=/app/data NODE_ENV=production
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/server.mjs"]
