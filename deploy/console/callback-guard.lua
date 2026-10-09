-- APISIX 3.19: plugin.filter resolves Secret references before rewrite.
-- Inspect only session presence; OIDC still validates state, PKCE and tokens.
return function(conf, ctx)
    if ngx.var.uri ~= "/console/callback" then
        return
    end
    if ngx.req.get_method() ~= "GET" then
        return 405
    end
    local options
    for i = 1, #(ctx.plugins or {}), 2 do
        if ctx.plugins[i].name == "openid-connect" then
            options = ctx.plugins[i + 1].session
            break
        end
    end
    if not options or not options.secret then
        return 503
    end
    -- open() reads/verifies the cookie without refreshing or saving it.
    local session = require("resty.session").open(options)
    local present = session and next(session:get_data()) ~= nil
    if session then
        session:close()
    end
    if present then
        return
    end
    -- No reflection of callback parameters and no automatic retry loop.
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Referrer-Policy"] = "no-referrer"
    ngx.header["X-Frame-Options"] = "SAMEORIGIN"
    ngx.header["X-Content-Type-Options"] = "nosniff"
    ngx.header["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'; base-uri 'none'"
    return 401, '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in again | Twinfra</title><h1>Start sign-in again</h1><p>Your sign-in session is missing or expired. The returned authorization code was not accepted.</p><p><a href="/console/">Start a fresh Twinfra sign-in</a></p></html>'
end
