# Geppetto Docker Plugin

Adds a `docker_container` operation for managing Docker containers via the Docker CLI.

## Installation
- Point Geppetto at this directory via `plugin_dirs` in your `main.conf`:
  ```toml
  [defaults]
  plugin_dirs = ["/home/dave/git/Geppetto_Plugins/Docker"]
  ```
- Ensure the `docker` CLI is available on the target host.

## Operation: docker_container
- `name` (string, required): Container name.
- `image` (string, required when `state=present`): Image to run.
- `state` (`present|absent`, default `present`): Create/ensure running or remove.
- `pull` (bool, default `true`): Pull the image before running.
- `detach` (bool, default `true`): Run container in detached mode.
- `restart` / `restart_policy` (string): Docker restart policy (e.g., `unless-stopped`, `on-failure`).
- `network` (string): Network to attach the container to.
- `workdir` (string): Working directory inside the container.
- `env` (map|string|list): Environment variables (`KEY=VALUE`).
- `ports` (list|string): Port mappings (`host:container[/proto]`).
- `volumes` (list|string): Volume mounts (`host:container[:options]`).
- `command` (string|list): Command/args to pass after the image.
- `extra_args` (list|string): Extra args passed before the image.
- `recreate` (bool, default `false`): Force remove + re-run the container.
- `recreate_on_image_change` (bool, default `true`): Recreate if the pulled image ID differs from the running container.

### Examples
Ensure an Nginx container is running and restart it when the image changes:
```
docker_container { 'nginx':
  image   => 'nginx:latest'
  ports   => ['80:80', '443:443']
  volumes => ['/srv/www:/usr/share/nginx/html:ro']
  restart => 'unless-stopped'
}
```

Run an app container with env vars and a specific command:
```
docker_container { 'myapp':
  image     => 'ghcr.io/acme/app:1.2.3'
  env       => { 'ENV' = 'prod', 'DEBUG' = '0' }
  ports     => ['8080:8080']
  command   => ['gunicorn', 'app:app', '-b', '0.0.0.0:8080']
  recreate  => true
}
```

Remove a container:
```
docker_container { 'old-app':
  state => 'absent'
}
```
