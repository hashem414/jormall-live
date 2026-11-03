module.exports=[88545,e=>{"use strict";let t=String.raw`(() => {
  "use strict";
  const script = document.currentScript;
  if (!script) return;
  const configurationToken = script.getAttribute("data-jormall-config");
  if (!configurationToken) return;
  const base = new URL(script.src).origin;
  const locale = script.getAttribute("data-locale") === "ar" ? "ar" : "en";
  let sessionToken = "";
  let labels;
  const host = document.createElement("div");
  host.setAttribute("data-jormall-ai-widget", "");
  document.body.append(host);
  const root = host.attachShadow({ mode: "open" });
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = base + "/ai-widget.css";
  root.append(stylesheet);

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  async function start() {
    const response = await fetch(base + "/api/ai/widget/session", {
      body: JSON.stringify({ configurationToken: configurationToken, locale: locale }),
      headers: { "content-type": "application/json" },
      method: "POST",
      mode: "cors"
    });
    if (!response.ok) throw new Error("WIDGET_SESSION_FAILED");
    const configuration = await response.json();
    sessionToken = configuration.sessionToken;
    labels = configuration.labels;
    host.style.setProperty("--jormall-primary", configuration.branding.primaryColor);
    host.style.setProperty("--jormall-accent", configuration.branding.accentColor);
    host.setAttribute("dir", configuration.direction);
    render(configuration);
  }

  function render(configuration) {
    const launcher = element("button", "launcher", labels.launcher);
    launcher.type = "button";
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-controls", "jormall-ai-panel");
    const panel = element("section", "panel");
    panel.id = "jormall-ai-panel";
    panel.hidden = true;
    panel.setAttribute("aria-label", configuration.branding.displayName);
    const header = element("header", "header");
    header.append(element("strong", "title", configuration.branding.displayName));
    const close = element("button", "close", "×");
    close.type = "button";
    close.setAttribute("aria-label", labels.close);
    header.append(close);
    const log = element("div", "log");
    log.setAttribute("aria-live", "polite");
    log.setAttribute("role", "log");
    const form = element("form", "composer");
    const messageLabel = element("label", "sr-only", labels.message);
    const input = element("input", "message");
    input.name = "message";
    input.maxLength = 5000;
    input.placeholder = labels.message;
    input.required = true;
    messageLabel.append(input);
    const send = element("button", "send", labels.send);
    send.type = "submit";
    form.append(messageLabel, send);
    panel.append(header, log);

    if (configuration.mockIdentityVerificationAvailable) {
      const details = element("details", "verification");
      const summary = element("summary", "verify-summary", labels.verify);
      const verifyForm = element("form", "verify-form");
      const phone = element("input", "verify-input");
      phone.placeholder = labels.verificationPhone;
      phone.setAttribute("aria-label", labels.verificationPhone);
      phone.required = true;
      const code = element("input", "verify-input");
      code.placeholder = labels.verificationCode;
      code.setAttribute("aria-label", labels.verificationCode);
      code.required = true;
      const verifyButton = element("button", "verify-button", labels.verify);
      verifyButton.type = "submit";
      verifyForm.append(phone, code, verifyButton);
      verifyForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        verifyButton.disabled = true;
        try {
          const response = await fetch(base + "/api/ai/widget/verify", {
            body: JSON.stringify({ phone: phone.value, sessionToken: sessionToken, verificationCode: code.value }),
            headers: { "content-type": "application/json" },
            method: "POST",
            mode: "cors"
          });
          if (!response.ok) throw new Error("VERIFY_FAILED");
          summary.textContent = labels.verified;
          details.open = false;
        } catch {
          appendMessage(log, labels.error, "assistant");
        } finally {
          verifyButton.disabled = false;
        }
      });
      details.append(summary, verifyForm);
      panel.append(details);
    }
    panel.append(form);
    root.append(panel, launcher);

    const toggle = (open) => {
      panel.hidden = !open;
      launcher.setAttribute("aria-expanded", String(open));
      if (open) input.focus();
    };
    launcher.addEventListener("click", () => toggle(panel.hidden));
    close.addEventListener("click", () => toggle(false));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      appendMessage(log, text, "customer");
      input.value = "";
      send.disabled = true;
      const assistant = appendMessage(log, "", "assistant");
      try {
        const response = await fetch(base + "/api/ai/widget/turn", {
          body: JSON.stringify({ message: text, requestId: crypto.randomUUID(), sessionToken: sessionToken }),
          headers: { "content-type": "application/json" },
          method: "POST",
          mode: "cors"
        });
        if (!response.ok || !response.body) throw new Error("TURN_FAILED");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffered = "";
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          buffered += decoder.decode(part.value, { stream: true });
          const lines = buffered.split("\n");
          buffered = lines.pop() || "";
          for (const line of lines) {
            if (!line) continue;
            const event = JSON.parse(line);
            if (event.type === "token") assistant.textContent += event.text;
            if (event.type === "error") assistant.textContent = labels.error;
            if (event.type === "takeover") assistant.textContent = "";
          }
        }
        if (!assistant.textContent) assistant.remove();
      } catch {
        assistant.textContent = labels.error;
      } finally {
        send.disabled = false;
        input.focus();
      }
    });
  }

  function appendMessage(log, text, role) {
    const message = element("p", "bubble " + role, text);
    message.dir = "auto";
    log.append(message);
    log.scrollTop = log.scrollHeight;
    return message;
  }

  start().catch(() => {
    host.remove();
  });
})();`;e.s(["GET",0,function(){return new Response(t,{headers:{"Access-Control-Allow-Origin":"*","Cache-Control":"public, max-age=300","Content-Type":"application/javascript; charset=utf-8","X-Content-Type-Options":"nosniff"}})}])},91528,e=>{"use strict";var t=e.i(7191),n=e.i(61230),a=e.i(44410),o=e.i(21861),r=e.i(75046),s=e.i(11407),i=e.i(88797),l=e.i(28790),d=e.i(63279),c=e.i(73839),u=e.i(24854),p=e.i(97255),h=e.i(66825),f=e.i(16864),m=e.i(81925),g=e.i(93695);e.i(39495);var v=e.i(47189);let b=new t.AppRouteRouteModule({definition:{kind:n.RouteKind.APP_ROUTE,page:"/ai-widget.js/route",pathname:"/ai-widget.js",filename:"route",bundlePath:""},distDir:".next",relativeProjectDir:"",resolvedPagePath:"[project]/apps/web/src/app/ai-widget.js/route.ts",nextConfigOutput:"standalone",userland:()=>e.r(88545),...{}}),{workAsyncStorage:y,workUnitAsyncStorage:R,serverHooks:w}=b;async function E(e,t,a){a.requestMeta&&(0,o.setRequestMeta)(e,a.requestMeta),b.isDev&&(0,o.addRequestMeta)(e,"devRequestTimingInternalsEnd",process.hrtime.bigint());let y="/ai-widget.js/route";y=y.replace(/\/index$/,"")||"/";let R=await b.prepare(e,t,{srcPage:y,multiZoneDraftMode:!1});if(!R)return t.statusCode=400,t.end("Bad Request"),null==a.waitUntil||a.waitUntil.call(a,Promise.resolve()),null;let{buildId:w,deploymentId:E,params:C,nextConfig:x,parsedUrl:A,isDraftMode:T,prerenderManifest:S,routerServerContext:N,isOnDemandRevalidate:k,revalidateOnlyGenerated:P,resolvedPathname:O,clientReferenceManifest:I,serverActionsManifest:_}=R,q=(0,i.normalizeAppPath)(y),j=!!(S.dynamicRoutes[q]||S.routes[O]),D=async()=>((null==N?void 0:N.render404)?await N.render404(e,t,A,!1):t.end("This page could not be found"),null);if(j&&!T){let e=!!S.routes[O],t=S.dynamicRoutes[q];if(t&&!1===t.fallback&&!e){if(x.adapterPath)return await D();throw new g.NoFallbackError}}let H=null;!j||b.isDev||T||(H="/index"===(H=O)?"/":H);let M=!0===b.isDev||!j,L=j&&!M;_&&I&&(0,s.setManifestsSingleton)({page:y,clientReferenceManifest:I,serverActionsManifest:_});let U=e.method||"GET",F=(0,r.getTracer)(),B=F.getActiveScopeSpan(),K=!!(null==N?void 0:N.isWrappedByNextServer),G=!!(0,o.getRequestMeta)(e,"minimalMode"),$=(0,o.getRequestMeta)(e,"incrementalCache")||await b.getIncrementalCache(e,x,S,G);null==$||$.resetRequestCache(),globalThis.__incrementalCache=$;let V={params:C,previewProps:S.preview,renderOpts:{experimental:{authInterrupts:!!x.experimental.authInterrupts,useCacheTimeout:x.experimental.useCacheTimeout},cacheComponents:!!x.cacheComponents,validationLevel:x.experimental.instantInsights.validationLevel,supportsDynamicResponse:M,incrementalCache:$,hmrRefreshHash:(0,o.getRequestMeta)(e,"hmrRefreshHash"),cacheLifeProfiles:x.cacheLife,staticPageGenerationTimeout:x.staticPageGenerationTimeout,waitUntil:a.waitUntil,onClose:e=>{t.on("close",e)},onAfterTaskError:void 0,onInstrumentationRequestError:(t,n,a,o)=>b.onRequestError(e,t,a,o,N)},sharedContext:{buildId:w,deploymentId:E}},J=new l.NodeNextRequest(e),X=new l.NodeNextResponse(t),W=d.NextRequestAdapter.fromNodeNextRequest(J,(0,d.signalFromNodeResponse)(t)),z=async({previousCacheEntry:n})=>{try{if(!G&&k&&P&&!n)return t.statusCode=404,t.setHeader("x-nextjs-cache","REVALIDATED"),t.end("This page could not be found"),null;let o=await b.handle(W,V);e.fetchMetrics=V.renderOpts.fetchMetrics;let r=V.renderOpts.pendingWaitUntil;r&&a.waitUntil&&(a.waitUntil(r),r=void 0);let s=V.renderOpts.collectedTags;if(!j)return await (0,p.sendResponse)(J,X,o,r),null;{let e=await o.blob(),t=(0,h.toNodeOutgoingHttpHeaders)(o.headers);s&&(t[m.NEXT_CACHE_TAGS_HEADER]=s),!t["content-type"]&&e.type&&(t["content-type"]=e.type);let n=void 0!==V.renderOpts.collectedRevalidate&&!(V.renderOpts.collectedRevalidate>=m.INFINITE_CACHE)&&V.renderOpts.collectedRevalidate,a=void 0===V.renderOpts.collectedExpire||V.renderOpts.collectedExpire>=m.INFINITE_CACHE?!1!==n&&n>0?x.expireTime:void 0:V.renderOpts.collectedExpire;return{value:{kind:v.CachedRouteKind.APP_ROUTE,status:o.status,body:Buffer.from(await e.arrayBuffer()),headers:t},cacheControl:{revalidate:n,expire:a}}}}catch(t){throw(null==n?void 0:n.isStale)&&await b.onRequestError(e,t,{routerKind:"App Router",routePath:y,routeType:"route",revalidateReason:(0,u.getRevalidateReason)({isStaticGeneration:L,isOnDemandRevalidate:k})},!1,N),t}},Y=async(o,s)=>{try{var i,l;let o=await b.handleResponse({req:e,nextConfig:x,cacheKey:H,routeKind:n.RouteKind.APP_ROUTE,isFallback:!1,prerenderManifest:S,isRoutePPREnabled:!1,isOnDemandRevalidate:k,revalidateOnlyGenerated:P,responseGenerator:z,waitUntil:a.waitUntil,isMinimalMode:G});if(!j)return;if((null==o||null==(i=o.value)?void 0:i.kind)!==v.CachedRouteKind.APP_ROUTE)throw Object.defineProperty(Error(`Invariant: app-route received invalid cache entry ${null==o||null==(l=o.value)?void 0:l.kind}`),"__NEXT_ERROR_CODE",{value:"E701",enumerable:!1,configurable:!0});G||t.setHeader("x-nextjs-cache",k?"REVALIDATED":o.isMiss?"MISS":o.isStale?"STALE":"HIT"),T&&t.setHeader("Cache-Control","private, no-cache, no-store, max-age=0, must-revalidate");let r=(0,h.fromNodeOutgoingHttpHeaders)(o.value.headers);G&&j||r.delete(m.NEXT_CACHE_TAGS_HEADER),!o.cacheControl||t.getHeader("Cache-Control")||r.get("Cache-Control")||r.set("Cache-Control",(0,f.getCacheControlHeader)(o.cacheControl)),await (0,p.sendResponse)(J,X,new Response(o.value.body,{headers:r,status:o.value.status||200}));return}catch(t){if(t instanceof g.NoFallbackError||await b.onRequestError(e,t,{routerKind:"App Router",routePath:q,routeType:"route",revalidateReason:(0,u.getRevalidateReason)({isStaticGeneration:L,isOnDemandRevalidate:k})},!1,N),j)throw t;await (0,p.sendResponse)(J,X,new Response(null,{status:500}));return}finally{(()=>{if(!o)return;let e=t.statusCode;o.setAttributes({"http.status_code":e,"next.rsc":!1}),e&&e>=500&&(o.setStatus({code:r.SpanStatusCode.ERROR}),o.setAttribute("error.type",e.toString()));let n=F.getRootSpanAttributes();if(!n)return;if(n.get("next.span_type")!==c.BaseServerSpan.handleRequest)return console.warn(`Unexpected root span type '${n.get("next.span_type")}'. Please report this Next.js issue https://github.com/vercel/next.js`);let a=n.get("next.route")||q,i=`${U} ${a}`;o.setAttributes({"next.route":a,"http.route":a,"next.span_name":i}),o.updateName(i),s&&s!==o&&(s.setAttribute("http.route",a),s.updateName(i))})()}};if(K&&B)await Y(B,void 0);else{let t=F.getActiveScopeSpan();await F.withPropagatedContext(e.headers,()=>F.trace(c.BaseServerSpan.handleRequest,{spanName:`${U} ${y}`,kind:r.SpanKind.SERVER,attributes:{"http.method":U,"http.target":e.url}},e=>Y(e,t)),void 0,!K)}}e.s(["handler",0,E,"patchFetch",0,function(){return(0,a.patchFetch)({workAsyncStorage:y,workUnitAsyncStorage:R})},"routeModule",0,b,"serverHooks",0,w,"workAsyncStorage",0,y,"workUnitAsyncStorage",0,R])}];

//# sourceMappingURL=_03rvyt8._.js.map