# Geppetto Plugins

Companion plugins that extend the Geppetto automation toolkit with extra operations without modifying core. Point Geppetto at this repository via `plugin_dirs` or install individual plugins as Python modules to make the operations available in your plans.

- Project home: https://github.com/daveseff/Geppetto
- Plugin catalog: this repo (`Geppetto_Plugins`)
  - `LetsEncrypt/`: manage Let's Encrypt certificates via certbot (webroot or standalone).
  - `Docker/`: manage Docker containers (create, recreate on image changes, remove).

## Usage

1) Add the plugins path to your `main.conf`:
```toml
[defaults]
plugin_dirs = ["/home/dave/git/Geppetto_Plugins/LetsEncrypt", "/home/dave/git/Geppetto_Plugins/Docker"]
```
2) Reference plugin operations in your plan, e.g.:
```fops
letsencrypt_cert { 'example-cert':
  domains => ['example.com']
  email   => 'admin@example.com'
  standalone => true
}

docker_container { 'nginx':
  image   => 'nginx:latest'
  ports   => ['80:80']
  restart => 'unless-stopped'
}
```

See each plugin directory for detailed options and examples. A single plugin can be enabled by pointing `plugin_dirs` to just that directory, or by listing an installed module under `plugin_modules`.
