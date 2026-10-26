// Light client-side gate. The app (markup + JS) is AES-256-GCM encrypted; the key is PBKDF2-SHA-256
// derived from the password. Only a salted SHA-256 verifier is stored, never the password.
(function () {
  var P = /*PAYLOAD*/null;
  var KEYSTORE = 'zg-demo-key';
  var b64 = function (s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; };
  var tob64 = function (u) { var s = ''; u = new Uint8Array(u); for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]); return btoa(s); };
  var hex = function (u) { return Array.prototype.map.call(new Uint8Array(u), function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); };
  var enc = new TextEncoder(), $ = function (id) { return document.getElementById(id); };
  function err(m) { $('gate-err').textContent = m; $('gate-pw').classList.toggle('bad', !!m); }
  function rawKey(pw) {
    return crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveBits']).then(function (k) {
      return crypto.subtle.deriveBits({ name: 'PBKDF2', salt: b64(P.salt), iterations: P.iter, hash: 'SHA-256' }, k, 256);
    });
  }
  function open(raw) {
    return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt'])
      .then(function (k) { return crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(P.iv) }, k, b64(P.ct)); })
      .then(function (pt) {
        var app = JSON.parse(new TextDecoder().decode(pt));
        $('app').innerHTML = app.html;
        var s = document.createElement('script'); s.textContent = app.js; document.body.appendChild(s);
        $('gate').remove(); document.body.classList.remove('locked');
        var lock = $('btn-lock'); if (lock) lock.onclick = function () { sessionStorage.removeItem(KEYSTORE); location.reload(); };
      });
  }
  var saved = sessionStorage.getItem(KEYSTORE);
  if (saved) open(b64(saved)).catch(function () { sessionStorage.removeItem(KEYSTORE); });
  if (!window.crypto || !crypto.subtle) err('This browser cannot unlock the demo (WebCrypto unavailable). Open it over https or from a local file in a modern browser.');
  $('gate-form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var pw = $('gate-pw').value; err(''); $('gate-btn').disabled = true; $('gate-btn').textContent = 'Unlocking…';
    var done = function () { $('gate-btn').disabled = false; $('gate-btn').textContent = 'Unlock demo'; };
    crypto.subtle.digest('SHA-256', enc.encode(P.hsalt + pw)).then(function (h) {
      if (hex(h) !== P.hash) { done(); err('That password is not right. Please try again.'); $('gate-pw').select(); return; }
      return rawKey(pw).then(function (raw) {
        return open(raw).then(function () { sessionStorage.setItem(KEYSTORE, tob64(raw)); });
      });
    }).catch(function () { done(); err('Could not unlock the demo. Please try again.'); });
  });
})();
