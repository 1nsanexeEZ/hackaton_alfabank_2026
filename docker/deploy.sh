#!/usr/bin/env bash
# Выкатка на VPS. Запускается из GitHub Actions: ssh … 'bash -s -- <sha>' < docker/deploy.sh
set -Eeuo pipefail

SHA="${1:?нужен sha коммита}"
APP_DIR="$HOME/hackaton_alfabank_2026"
cd "$APP_DIR"

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
  docker compose up -d --build --remove-orphans
}
trap rollback ERR

docker compose config --quiet
docker compose build --pull          # старая версия пока работает
docker compose up -d --remove-orphans --wait --wait-timeout 300
docker compose exec -T backend python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=5)"

trap - ERR
docker image prune -f
docker compose ps
echo "Выкачено: $SHA"
