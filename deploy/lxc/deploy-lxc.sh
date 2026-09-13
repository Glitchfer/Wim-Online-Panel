#!/usr/bin/env bash
# deploy-lxc.sh — Create 4 Proxmox LXCs for WIM Online (wim-db, wim-api, sales-app, admin-panel)
# Run on the Proxmox host. Requires a Debian 12 LXC template already downloaded.
#
# Usage: bash deploy-lxc.sh   (use default VMIDs)
#        VMID_DB=107 VMID_API=108 bash deploy-lxc.sh

set -euo pipefail

TEMPLATE="${TEMPLATE:-local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst}"
STORE="${STORE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"

# VMIDs (override via env)
VMID_DB="${VMID_DB:-107}"
VMID_API="${VMID_API:-108}"
VMID_SALES="${VMID_SALES:-109}"
VMID_ADMIN="${VMID_ADMIN:-110}"

PG_PASS="${POSTGRES_PASSWORD:-wim_postgres_2026}"
PG_IP="${PG_IP:-192.168.6.30}"
API_IP="${API_IP:-192.168.6.31}"
SALES_IP="${SALES_IP:-192.168.6.32}"
ADMIN_IP="${ADMIN_IP:-192.168.6.33}"

echo "Creating wim-db LXC ${VMID_DB}"
pct create "$VMID_DB" "$TEMPLATE" --hostname wim-db --memory 1024 --cores 1 \
  --storage "$STORE" --net0 name=eth0,bridge="$BRIDGE",ip="$PG_IP/24",gw=192.168.6.1
pct start "$VMID_DB"

echo "Creating wim-api LXC ${VMID_API}"
pct create "$VMID_API" "$TEMPLATE" --hostname wim-api --memory 1024 --cores 1 \
  --storage "$STORE" --net0 name=eth0,bridge="$BRIDGE",ip="$API_IP/24",gw=192.168.6.1
pct start "$VMID_API"

echo "Creating sales-app LXC ${VMID_SALES}"
pct create "$VMID_SALES" "$TEMPLATE" --hostname sales-app --memory 512 --cores 1 \
  --storage "$STORE" --net0 name=eth0,bridge="$BRIDGE",ip="$SALES_IP/24",gw=192.168.6.1
pct start "$VMID_SALES"

echo "Creating admin-panel LXC ${VMID_ADMIN}"
pct create "$VMID_ADMIN" "$TEMPLATE" --hostname admin-panel --memory 512 --cores 1 \
  --storage "$STORE" --net0 name=eth0,bridge="$BRIDGE",ip="$ADMIN_IP/24",gw=192.168.6.1
pct start "$VMID_ADMIN"

echo ""
echo "All 4 LXCs created & started."
echo "Next: provision each (apt update, copy code, systemd units). See DEPLOYMENT.md §8."
echo "  wim-db:      $PG_IP   (PostgreSQL 17, db=$POSTGRES_PASSWORD password)"
echo "  wim-api:     $API_IP"
echo "  sales-app:   $SALES_IP"
echo "  admin-panel: $ADMIN_IP"