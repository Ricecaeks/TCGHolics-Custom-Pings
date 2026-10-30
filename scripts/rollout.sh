#!/usr/bin/env bash
# Rolling update across the NUCs, one node at a time. Each node must be healthy before the
# next one restarts, so monitoring never stops completely.
#
#   scripts/rollout.sh nuc1 nuc2 nuc3
#
# Assumes SSH access to each host and the repo cloned at $REMOTE_DIR (default ~/TCGHolics-Custom-Pings).
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <ssh-host> [<ssh-host> ...]" >&2
  exit 2
fi

REMOTE_DIR=${REMOTE_DIR:-'~/TCGHolics-Custom-Pings'}
COMPOSE="docker compose -f deploy/docker-compose.yml"

for node in "$@"; do
  echo "==> $node: updating"
  ssh "$node" "cd $REMOTE_DIR && git pull --ff-only && $COMPOSE up -d --build"

  status=unknown
  for _ in $(seq 1 36); do
    status=$(ssh "$node" "cd $REMOTE_DIR && docker inspect -f '{{.State.Health.Status}}' \$($COMPOSE ps -q tcgpings)" || true)
    [ "$status" = "healthy" ] && break
    sleep 5
  done
  if [ "$status" != "healthy" ]; then
    echo "!! $node is '$status' after 3 minutes; stopping the rollout here" >&2
    echo "   check: ssh $node 'cd $REMOTE_DIR && $COMPOSE logs --tail 100'" >&2
    exit 1
  fi
  echo "==> $node: healthy"
done
echo "rollout complete"
