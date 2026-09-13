# Future Integration — API Endpoint Stubs

> This document defines the **API stubs** for future external integrations.
> These endpoints are NOT required for V1. They will be implemented after the standalone
> PostgreSQL architecture has stabilized.

## Architecture Overview

```
┌──────────────────────────────────────────────┐
│             WIM Online (PostgreSQL wim_sfa)    │
└──────────────────────┬───────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
┌─────────────────┐ ┌────────┐ ┌──────────────┐
│  Fleetbase API  │ │ Odoo   │ │ Warehouse    │
│  (orders/stores)│ │ (repts)│ │ (inventory)  │
└─────────────────┘ └────────┘ └──────────────┘
```

---

## 1. Fleetbase Sync Endpoints

### Purpose
Bidirectional sync of orders and stores between WIM Online and Fleetbase LSOS.
- Push: new WIM orders → Fleetbase orders, new WIM stores → Fleetbase places
- Pull: Fleetbase orders → WIM order history, Fleetbase places → WIM stores

### Endpoints

#### `POST /api/sync/fleetbase/orders/push`

Push new orders from WIM Online to Fleetbase.

**Request:**
```json
{
  "orders": [
    {
      "wim_order_id": "ORD-20260909-001",
      "store_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "customer_name": "TOKO BERKAH",
      "items": [
        {"sku": "SQA-PET-550ML", "name": "SANQUA PET 550ML", "qty": 10, "price": 5000},
        {"sku": "SQA-CUP-120ML", "name": "SANQUA CUP 120ML", "qty": 5, "price": 3000}
      ],
      "total": 65000,
      "payment_method": "cod",
      "status": "pending",
      "ordered_at": "2026-09-09T08:30:00+07:00",
      "driver_uuid": "660e8400-e29b-41d4-a716-446655440001",
      "meta": {
        "checkin_id": "770e8400-e29b-41d4-a716-446655440002",
        "off_route": false,
        "promos_applied": ["BUNDLE-SQA-10"],
        "sales_channel": "app"
      }
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "synced": 1,
  "failed": 0,
  "fleetbase_refs": {
    "ORD-20260909-001": "fleetbase_order_abc123"
  },
  "errors": []
}
```

#### `POST /api/sync/fleetbase/orders/pull`

Pull orders created in Fleetbase (admin orders, customer self-orders) into WIM Online.

**Request:**
```json
{
  "since": "2026-09-01T00:00:00+07:00",
  "until": "2026-09-09T23:59:59+07:00",
  "status": ["pending", "shipped", "completed"]
}
```

**Response:**
```json
{
  "success": true,
  "orders": [
    {
      "fleetbase_order_id": "fleetbase_order_def456",
      "store_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "customer_name": "TOKO ABC",
      "items": [
        {"sku": "LEV-CUP-220ML", "name": "LEVONTE CUP 220ML", "qty": 20, "price": 4000}
      ],
      "total": 80000,
      "payment_method": "cod",
      "status": "shipped",
      "ordered_at": "2026-09-05T10:00:00+07:00",
      "source": "admin",
      "meta": {}
    }
  ],
  "total_pulled": 1
}
```

#### `POST /api/sync/fleetbase/stores/push`

Push new stores from WIM Online to Fleetbase as Places.

**Request:**
```json
{
  "stores": [
    {
      "wim_store_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "TOKO BERKAH BARU",
      "owner_name": "Budi Santoso",
      "phone": "6281234567890",
      "address": {
        "street": "Jl. Contoh No. 123",
        "city": "Jakarta",
        "province": "DKI Jakarta",
        "district": "Tanah Abang",
        "subdistrict": "Bendungan Hilir",
        "postal_code": "10210"
      },
      "coordinates": {"lat": -6.2088, "lng": 106.8456},
      "channel": "GT",
      "category": "Retail Kecil",
      "vehicle_type": "Motor",
      "meta": {
        "nik": "3273010101900001",
        "npwp": "99.999.999.9-999.999"
      }
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "synced": 1,
  "failed": 0,
  "fleetbase_refs": {
    "550e8400-e29b-41d4-a716-446655440000": "fleetbase_place_ghi789"
  },
  "errors": []
}
```

#### `POST /api/sync/fleetbase/stores/pull`

Pull stores/places from Fleetbase into WIM Online.

**Request:**
```json
{
  "since": "2026-09-01T00:00:00+07:00"
}
```

**Response:**
```json
{
  "success": true,
  "stores": [
    {
      "fleetbase_place_id": "fleetbase_place_jkl012",
      "name": "TOKO IMPORTED",
      "owner_name": "Slamet Riyadi",
      "phone": "6289876543210",
      "address": {
        "street": "Jl. Merdeka No. 45",
        "city": "Bandung",
        "province": "Jawa Barat"
      },
      "coordinates": {"lat": -6.9147, "lng": 107.6098},
      "channel": "MT",
      "category": "Supermarket"
    }
  ],
  "total_pulled": 1
}
```

#### `GET /api/sync/fleetbase/status`

Get sync status and last sync timestamps.

**Response:**
```json
{
  "last_orders_push": "2026-09-09T10:00:00+07:00",
  "last_orders_pull": "2026-09-09T09:00:00+07:00",
  "last_stores_push": "2026-09-08T15:00:00+07:00",
  "last_stores_pull": "2026-09-08T14:00:00+07:00",
  "pending_orders": 3,
  "pending_stores": 0,
  "sync_enabled": true
}
```

---

## 2. Odoo Sync Endpoints

### Purpose
Push WIM Online sales data into Odoo ERP for accounting, reporting, and inventory tracking.

#### `POST /api/sync/odoo/reports/push`

Push daily/monthly sales reports to Odoo.

**Request:**
```json
{
  "period": {
    "from": "2026-09-01",
    "to": "2026-09-09"
  },
  "reports": {
    "sales_summary": {
      "total_omset": 4316118114,
      "total_invoices": 28959,
      "total_qty": 179313,
      "unique_stores": 21298,
      "avg_order_value": 149043
    },
    "by_depot": [
      {"depot": "JABAR", "omset": 1200000000, "invoices": 8500, "qty": 52000},
      {"depot": "JATIM", "omset": 980000000, "invoices": 7200, "qty": 48000},
      {"depot": "JATENG", "omset": 750000000, "invoices": 5400, "qty": 35000}
    ],
    "by_salesperson": [
      {"sales_id": "S001", "name": "Agus", "omset": 150000000, "visits": 45, "orders": 30},
      {"sales_id": "S002", "name": "Bambang", "omset": 135000000, "visits": 42, "orders": 28}
    ],
    "top_products": [
      {"sku": "SQA-PET-550ML", "name": "SANQUA PET 550ML", "qty": 25000, "omset": 125000000},
      {"sku": "LEV-CUP-220ML", "name": "LEVONTE CUP 220ML", "qty": 18000, "omset": 72000000}
    ]
  }
}
```

**Response:**
```json
{
  "success": true,
  "odoo_ref": "odoo_report_20260909",
  "processed_at": "2026-09-09T11:00:00+07:00"
}
```

#### `GET /api/sync/odoo/products`

Pull product catalog from Odoo.

**Response:**
```json
{
  "products": [
    {
      "odoo_product_id": 12345,
      "sku": "SQA-PET-550ML",
      "name": "SANQUA PET 550ML",
      "category": "Air Mineral",
      "brand": "SANQUA",
      "uom": "KARTON",
      "price": 5000,
      "active": true
    }
  ],
  "total": 150
}
```

#### `POST /api/sync/odoo/orders/push`

Push completed orders to Odoo for invoicing.

**Request:**
```json
{
  "orders": [
    {
      "wim_order_id": "ORD-20260909-001",
      "odoo_partner_id": 9876,
      "invoice_date": "2026-09-09",
      "items": [
        {"sku": "SQA-PET-550ML", "qty": 10, "price": 5000},
        {"sku": "SQA-CUP-120ML", "qty": 5, "price": 3000}
      ],
      "total": 65000,
      "payment_term": "COD",
      "notes": "Free delivery promo"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "invoices_created": 1,
  "odoo_invoice_ids": [45001],
  "errors": []
}
```

---

## 3. Warehouse Sync Endpoints

### Purpose
Synchronize inventory and stock levels between WIM Online and warehouse management systems.

#### `POST /api/sync/warehouse/inventory/pull`

Pull current inventory levels from warehouse system.

**Request:**
```json
{
  "depot_id": "JABAR",
  "brands": ["SANQUA", "LEVONTE"]
}
```

**Response:**
```json
{
  "success": true,
  "inventory": [
    {"sku": "SQA-PET-550ML", "name": "SANQUA PET 550ML", "available_qty": 1500, "uom": "KARTON"},
    {"sku": "SQA-PET-220ML", "name": "SANQUA PET 220ML", "available_qty": 3200, "uom": "KARTON"},
    {"sku": "LEV-CUP-220ML", "name": "LEVONTE CUP 220ML", "available_qty": 800, "uom": "KARTON"}
  ],
  "synced_at": "2026-09-09T06:00:00+07:00"
}
```

#### `POST /api/sync/warehouse/stock/push`

Push stock check data from sales visits to warehouse system.

**Request:**
```json
{
  "stock_checks": [
    {
      "store_uuid": "550e8400-e29b-41d4-a716-446655440000",
      "store_name": "TOKO BERKAH",
      "checked_at": "2026-09-09T08:30:00+07:00",
      "checked_by": "Agus (S001)",
      "items": [
        {"sku": "SQA-PET-550ML", "qty_on_hand": 5},
        {"sku": "SQA-PET-220ML", "qty_on_hand": 12},
        {"sku": "LEV-CUP-220ML", "qty_on_hand": 3}
      ]
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "synced": 1,
  "warehouse_refs": {
    "stock_001": "wh_stock_update_abc"
  }
}
```

#### `POST /api/sync/warehouse/delivery/status`

Update delivery/shipment status from warehouse.

**Request:**
```json
{
  "deliveries": [
    {
      "wim_order_id": "ORD-20260909-001",
      "status": "shipped",
      "tracking_number": "JNE-1234567890",
      "shipped_at": "2026-09-09T14:00:00+07:00",
      "items": [
        {"sku": "SQA-PET-550ML", "qty_shipped": 10},
        {"sku": "SQA-CUP-120ML", "qty_shipped": 5}
      ]
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "updated": 1,
  "failed": 0
}
```

---

## 4. Error Handling (All Sync Endpoints)

All sync endpoints use the same error response format:

```json
{
  "success": false,
  "error": {
    "code": "UPSTREAM_UNAVAILABLE",
    "message": "Fleetbase API is unreachable (timeout after 30s)",
    "retry_after": 60
  }
}
```

### Common Error Codes

| Code | Description | Retry Strategy |
|------|-------------|----------------|
| `UPSTREAM_UNAVAILABLE` | External API is down | Retry with exponential backoff (30s, 60s, 120s, 300s max) |
| `RATE_LIMITED` | External API rate limit hit | Retry after `retry_after` seconds |
| `INVALID_PAYLOAD` | Request data failed validation | Do not retry — check payload |
| `CONFLICT` | Data conflict (e.g., order already synced) | Log and skip |
| `AUTH_FAILED` | API key or token expired | Alert admin, stop sync |

### Sync Schedule (Recommended)

| Integration | Frequency | Notes |
|-------------|-----------|-------|
| Fleetbase orders push | Every 5 minutes | Near-real-time order sync |
| Fleetbase orders pull | Every 15 minutes | Import admin/customer orders |
| Fleetbase stores push | On NOO creation | Real-time store sync |
| Fleetbase stores pull | Daily (02:00) | Nightly store reconciliation |
| Odoo reports push | Daily (03:00) | End-of-day sales report |
| Odoo products pull | Daily (04:00) | Product catalog refresh |
| Warehouse inventory pull | Every 30 minutes | Stock availability for sales |
| Warehouse stock push | On stock check | Real-time store stock data |

---

## 5. Implementation Notes

1. **Idempotency:** All sync endpoints are idempotent — calling the same payload twice produces the same result (no duplicate orders/stores/reports).
2. **Retry queue:** Failed sync operations should be queued in a `wim_sync_queue` table with retry count, last error, and next retry timestamp.
3. **Auth:** Each external integration uses its own API key/credential stored in environment variables:
   - `FLEETBASE_API_KEY`, `FLEETBASE_API_URL`
   - `ODOO_API_KEY`, `ODOO_API_URL`, `ODOO_DB`
   - `WAREHOUSE_API_KEY`, `WAREHOUSE_API_URL`
4. **Audit log:** All sync operations are logged to `wim_sync_log` (action, entity type, external ref, status, timestamp).
5. **Feature flag:** Each integration has a toggle in depot config: `sync_fleetbase_enabled`, `sync_odoo_enabled`, `sync_warehouse_enabled`.