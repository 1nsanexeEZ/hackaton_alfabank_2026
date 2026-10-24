#!/usr/bin/env bash
# Выкатка на VPS. Запускается из GitHub Actions: ssh … 'bash -s -- <sha>' < docker/deploy.sh
set -Eeuo pipefail

SHA="${1:?нужен sha коммита}"
APP_DIR="$HOME/hackaton_alfabank_2026"
cd "$APP_DIR"

# Стенд = базовый compose + добавка docker-compose.prod.yml (HTTPS, Basic Auth, порты 80 и 443).
# Добавку ищем в том коммите, что сейчас выкачен: в старых версиях её нет, и откат на них
# идёт тем же базовым compose, что раньше.
dc() {
  if [[ -f docker-compose.prod.yml ]]; then
    docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
  else
    docker compose "$@"
  fi
}

docker compose version >/dev/null 2>&1 || { echo "Нужен Docker Compose v2 (docker compose)"; exit 1; }

for f in .env docker/nginx/.htpasswd; do
  [[ -f $f ]] || { echo "Нет $APP_DIR/$f, создайте вручную"; exit 1; }
done

export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/github_deploy_key -o IdentitiesOnly=yes"
PREV_SHA="$(git rev-parse HEAD)"

git fetch --force --tags origin
git checkout --force --detach "$SHA"

rollback() {
  echo "Деплой $SHA не прошёл, откат на $PREV_SHA"
  git checkout --force --detach "$PREV_SHA"
  dc up -d --build --remove-orphans
}
trap rollback ERR

dc config --quiet                    # заодно проверяет, что Compose понимает !override (нужен 2.24.4+)
dc build --pull                      # старая версия пока работает
dc up -d --remove-orphans --wait --wait-timeout 300
dc exec -T backend python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=5)"
dc port nginx 443 >/dev/null         # стенд должен слушать HTTPS, а не локальный 8080

trap - ERR
docker image prune -f
dc ps
echo "Выкачено: $SHA"
