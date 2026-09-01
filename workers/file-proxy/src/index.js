/**
 * Signed R2 file proxy.
 *
 * Fronts the R2 bucket so the app never hands a browser a raw AWS-SigV4 presigned URL
 * (a long-lived bearer credential usable by anyone who sees it, e.g. in incognito or
 * via a shared link). Instead the Flask app signs a short-lived HMAC token per request
 * (see r2_client.generate_worker_url); this Worker validates it and streams the object
 * straight from R2 over the Worker<->R2 binding, so bytes never round-trip through the
 * app server and the R2 host/credentials are never exposed to the client.
 *
 * URL shape: GET /<object-key>?exp=<unix-ts>&sig=<hmac-hex>&dl=<0|1>&filename=<name>
 */
// CORS is safe to leave wide open here: the URL's own HMAC signature + expiry is the real
// access control (see the module docstring), not the requesting origin — a client-side
// fetch() (e.g. the spreadsheet viewer parsing raw bytes with SheetJS) needs
// Access-Control-Allow-Origin to read the response at all, unlike a plain <img>/<iframe>/
// <video> src, which never triggers a CORS check in the first place.
function withCors(response) {
  response.headers.set('Access-Control-Allow-Origin', '*');
  return response;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = decodeURIComponent(url.pathname.slice(1));
    const exp = url.searchParams.get('exp');
    const sig = url.searchParams.get('sig');
    const dl = url.searchParams.get('dl') === '1';
    const filenameParam = url.searchParams.get('filename') || '';

    if (!key || !exp || !sig) {
      return withCors(new Response('Missing parameters', { status: 400 }));
    }

    const expNum = Number(exp);
    if (!Number.isFinite(expNum) || Math.floor(Date.now() / 1000) > expNum) {
      return withCors(new Response('Link expired', { status: 403 }));
    }

    const message = `${key}:${exp}:${dl ? '1' : '0'}:${filenameParam}`;
    const expectedSig = await hmacHex(env.SIGNING_SECRET, message);
    if (!timingSafeEqual(expectedSig, sig)) {
      return withCors(new Response('Invalid signature', { status: 403 }));
    }

    const object = await env.FILES_BUCKET.get(key);
    if (!object) {
      return withCors(new Response('Not found', { status: 404 }));
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('etag', object.httpEtag);
    headers.set('Cache-Control', 'private, no-store');
    if (dl) {
      // Overrides the inline disposition stored at upload time — a download link always
      // wants "Save As", regardless of how the object serves for in-app viewing.
      const filename = (filenameParam || key.split('/').pop() || 'download').replace(/"/g, '');
      headers.set('Content-Disposition', `attachment; filename="${filename}"`);
    }

    return withCors(new Response(object.body, { headers }));
  },
};

async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const sigBuf = await crypto.subtle.sign('HMAC', cryptoKey, enc.encode(message));
  return [...new Uint8Array(sigBuf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i += 1) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}
