#!/bin/bash
# HW8: create every s9486_ topic by hand (auto-create is turned off in docker-compose.yml).
# Runs inside the Kafka container:  make kafka-topics   (the kafka-init service also runs it on `make kafka-up`)
set -e
BS="${1:-kafka:29092}"
KT=/opt/kafka/bin/kafka-topics.sh

create() {
  echo "creating $1 with $2 partition(s)"
  $KT --bootstrap-server "$BS" --create --if-not-exists --topic "$1" --partitions "$2" --replication-factor 1
}

create s9486_entity_requests 1
create s9486_entity_responses 1
create s9486_inbox 1
create s9486_tasks 2
create s9486_drafts 1
create s9486_final 1
create s9486_dead_letter 1

echo "--- s9486 topics on $BS"
$KT --bootstrap-server "$BS" --describe | grep -E "^Topic: s9486_" | awk '{print $1, $2, $5, $6, $7, $8}'
