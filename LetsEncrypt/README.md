# Geppetto Let's Encrypt Plugin

Adds a `letsencrypt_cert` operation that issues or renews certificates with certbot using either the webroot HTTP-01 challenge or the standalone challenge.

## Installation
- Point Geppetto at this directory via `plugin_dirs` in your `main.conf`:
  ```toml
  [defaults]
  plugin_dirs = ["/etc/geppetto/plugins/LetsEncrypt"]
  ```
- Ensure `certbot` and `openssl` are available on the target host.

## Operation: letsencrypt_cert
- `domains` (list or string, required): Domain names to include on the certificate.
- `email` (string, required): Registration email for Let's Encrypt.
- `webroot` (string, optional): Path served over HTTP for the HTTP-01 challenge. If omitted, the standalone challenge is used.
- `standalone` (bool, default auto): Force the standalone challenge (useful when you want certbot to bind to port 80/443 instead of serving from a webroot).
- `cert_name` (string, default first domain): Name used under `/etc/letsencrypt/live/<cert_name>`.
- `renew_before_days` (int, default 30): Renew when expiry is within this many days.
- `force_renew` (bool): Force renewal even if still valid.
- `staging` (bool): Use Let's Encrypt staging endpoint for testing.
- `extra_args` (list): Extra flags passed to certbot.
- `state` (`present|absent`, default `present`): Issue/renew or delete the certificate.

### Example plan snippet
```
letsencrypt_cert { 'example-cert':
  domains           => ['example.com', 'www.example.com']
  email             => 'admin@example.com'
  webroot           => '/var/www/html'
  cert_name         => 'example.com'
  renew_before_days => 21
  staging           => false
}
```

Delete a certificate:
```
letsencrypt_cert { 'cleanup-old-cert':
  cert_name => 'old.example.com'
  state     => 'absent'
}
```

During dry-run the operation reports the intended change but skips calling certbot.

Standalone challenge example (no web server needed, but port 80/443 must be free/open):
```
letsencrypt_cert { 'example-standalone':
  domains => ['example.com']
  email   => 'admin@example.com'
  standalone => true
}
```
