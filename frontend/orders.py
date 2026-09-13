"""WIM Online — Order Management Module
Imported by serve.py for cart, product catalog, promo engine, and order creation.
"""
import json, time, datetime, uuid as uuid_mod
from urllib.parse import urlparse, parse_qs

# ── Products catalog (from entities)
def do_products(handler):
    user = handler._require_auth()
    if not user: return
    qs = parse_qs(urlparse(handler.path).query)
    brand = (qs.get('brand') or [''])[0].strip()
    search = (qs.get('q') or [''])[0].strip()
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()
        where = "WHERE type='product' AND deleted_at IS NULL"
        params = []
        if brand:
            where += " AND JSON_UNQUOTE(JSON_EXTRACT(meta, '$.brand'))=%s"
            params.append(brand)
        if search:
            where += " AND (name LIKE %s OR sku LIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])
        cur.execute(f"SELECT uuid, name, sku, meta, description, weight, weight_unit FROM entities {where} ORDER BY name", params)
        products = []
        for r in cur.fetchall():
            m = r['meta']
            if isinstance(m, str):
                try: m = json.loads(m)
                except: m = {}
            price = (m.get('price') if isinstance(m, dict) else None) or 0
            brand_name = (m.get('brand') if isinstance(m, dict) else None) or ''
            category = (m.get('category') if isinstance(m, dict) else None) or ''
            products.append({
                'uuid': r['uuid'], 'name': r['name'], 'sku': r['sku'],
                'price': price, 'brand': brand_name, 'category': category,
                'description': r['description'] or '',
                'weight': float(r['weight'] or 0), 'weightUnit': r['weight_unit'] or 'pcs'
            })
        cur.close()
        ret_mysql(conn)
        brands = sorted(set(p['brand'] for p in products if p['brand']))
        handler._send_json(200, {'products': products, 'brands': brands, 'total': len(products)})
    except Exception as e:
        write_log('ERROR', 'products', f'GET failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Active promos
def do_promos(handler):
    user = handler._require_auth()
    if not user: return
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.promo_ref, p.nama, p.jenis, p.status, p.priority, p.stackable,
                   p.periode_start, p.periode_end, p.min_transaction_amount, p.max_discount_amount,
                   pc.condition_type, pc.condition_value,
                   pr.reward_type, pr.reward_value, pr.reward_sku_ref, pr.reward_qty
            FROM wim_promo p
            LEFT JOIN wim_promo_conditions pc ON p.id=pc.promo_id
            LEFT JOIN wim_promo_rewards pr ON p.id=pr.promo_id
            WHERE p.status='active' AND (p.periode_end IS NULL OR p.periode_end >= CURDATE())
            AND p.deleted_at IS NULL
            ORDER BY p.priority, p.id
        """)
        promos_dict = {}
        for r in cur.fetchall():
            pid = r['id']
            if pid not in promos_dict:
                promos_dict[pid] = {
                    'id': pid, 'promoRef': r['promo_ref'], 'nama': r['nama'],
                    'jenis': r['jenis'], 'priority': r['priority'], 'stackable': bool(r['stackable']),
                    'periodeStart': str(r['periode_start']) if r['periode_start'] else None,
                    'periodeEnd': str(r['periode_end']) if r['periode_end'] else None,
                    'minTransaction': float(r['min_transaction_amount'] or 0),
                    'maxDiscount': float(r['max_discount_amount'] or 0),
                    'conditions': [], 'rewards': []
                }
            if r['condition_type']:
                cv = r['condition_value']
                if isinstance(cv, str):
                    try: cv = json.loads(cv)
                    except: pass
                promos_dict[pid]['conditions'].append({'type': r['condition_type'], 'value': cv})
            if r['reward_type']:
                rv = r['reward_value']
                if isinstance(rv, str):
                    try: rv = json.loads(rv)
                    except: pass
                promos_dict[pid]['rewards'].append({
                    'type': r['reward_type'], 'value': rv,
                    'skuRef': r['reward_sku_ref'], 'qty': r['reward_qty']
                })
        cur.close()
        ret_mysql(conn)
        handler._send_json(200, {'promos': list(promos_dict.values())})
    except Exception as e:
        write_log('ERROR', 'promos', f'GET failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Order calculate (server-side promo engine)
def do_order_calc(handler, data):
    user = handler._require_auth()
    if not user: return
    items = data.get('items', [])
    if not items:
        return handler._send_json(400, {'error': 'items diperlukan'})
    try:
        conn = get_mysql()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.promo_ref, p.nama, p.jenis, p.priority, p.stackable,
                   pc.condition_type, pc.condition_value,
                   pr.reward_type, pr.reward_value, pr.reward_sku_ref, pr.reward_qty
            FROM wim_promo p
            LEFT JOIN wim_promo_conditions pc ON p.id=pc.promo_id
            LEFT JOIN wim_promo_rewards pr ON p.id=pr.promo_id
            WHERE p.status='active' AND (p.periode_end IS NULL OR p.periode_end >= CURDATE())
            AND p.deleted_at IS NULL
            ORDER BY p.priority, p.id
        """)
        promos_raw = {}
        for r in cur.fetchall():
            pid = r['id']
            if pid not in promos_raw:
                promos_raw[pid] = {'jenis': r['jenis'], 'priority': r['priority'], 'stackable': r['stackable'], 'promoRef': r['promo_ref'], 'nama': r['nama'], 'conditions': [], 'rewards': []}
            if r['condition_type']:
                cv = r['condition_value']
                if isinstance(cv, str) and cv.startswith('{'): cv = json.loads(cv)
                promos_raw[pid]['conditions'].append({'type': r['condition_type'], 'value': cv})
            if r['reward_type']:
                rv = r['reward_value']
                if isinstance(rv, str) and rv.startswith('{'): rv = json.loads(rv)
                promos_raw[pid]['rewards'].append({'type': r['reward_type'], 'value': rv, 'skuRef': r['reward_sku_ref'], 'qty': r['reward_qty']})
        cur.close()
        ret_mysql(conn)

        purchased = [i for i in items if not i.get('is_bonus')]
        bonus = [i for i in items if i.get('is_bonus')]
        applied_promos = []

        for pid, promo in sorted(promos_raw.items(), key=lambda x: x[1]['priority']):
            jen = promo['jenis']
            conds = promo['conditions']
            rewards = promo['rewards']
            if jen == 'bundling':
                purchase_sku = None
                min_qty = 0
                for c in conds:
                    if c['type'] == 'purchase_sku': purchase_sku = c['value'].get('sku')
                    if c['type'] == 'purchase_qty_min': min_qty = c['value'].get('qty', 0)
                if purchase_sku and min_qty > 0:
                    cart_qty = sum(i['qty'] for i in purchased if i['sku'] == purchase_sku)
                    if cart_qty >= min_qty:
                        for r in rewards:
                            if r['type'] == 'free_sku':
                                free_sku = r['skuRef'] or (r['value'].get('sku') if isinstance(r['value'], dict) else '')
                                free_qty = int(r['qty'] or 1)
                                if free_sku:
                                    existing = next((b for b in bonus if b['sku'] == free_sku), None)
                                    bonus_qty = free_qty * (cart_qty // min_qty)
                                    if existing:
                                        existing['qty'] += bonus_qty
                                    else:
                                        sku_info = next((i for i in items if i['sku'] == free_sku), {})
                                        bonus.append({'sku': free_sku, 'name': sku_info.get('name', ''), 'qty': bonus_qty, 'is_bonus': True, 'promoName': promo['nama'], 'promoRef': promo['promoRef']})
                                    applied_promos.append({'promoRef': promo['promoRef'], 'nama': promo['nama'], 'jenis': 'bundling'})

            elif jen == 'strata':
                discount_pct = 0
                for c in conds:
                    if c['type'] == 'eligible_sku_category':
                        total_qty = sum(i['qty'] for i in purchased)
                        for r in sorted(rewards, key=lambda x: x['value'].get('min_qty', 0) if isinstance(x['value'], dict) else 0, reverse=True):
                            rv = r['value']
                            if isinstance(rv, dict) and rv.get('min_qty', 0) <= total_qty:
                                discount_pct = rv.get('pct', 0)
                                break
                        if discount_pct > 0:
                            applied_promos.append({'promoRef': promo['promoRef'], 'nama': promo['nama'], 'jenis': 'strata', 'discountPct': discount_pct})

            elif jen == 'diskon':
                for c in conds:
                    if c['type'] == 'purchase_sku':
                        sku = c['value'].get('sku')
                        for r in rewards:
                            if r['type'] == 'discount_amount':
                                amt = r['value'].get('amount', 0) if isinstance(r['value'], dict) else 0
                                for i in purchased:
                                    if i['sku'] == sku:
                                        i['unitDiscount'] = (i.get('unitDiscount') or 0) + amt
                                        applied_promos.append({'promoRef': promo['promoRef'], 'nama': promo['nama'], 'jenis': 'diskon', 'amount': amt})

        subtotal = sum(i['qty'] * (i.get('unitPrice', 0)) for i in purchased)
        total_discount = sum(i.get('unitDiscount', 0) * i['qty'] for i in purchased)
        strata_discount = 0
        for ap in applied_promos:
            if ap.get('jenis') == 'strata':
                pct = ap.get('discountPct', 0)
                strata_discount = subtotal * pct / 100
        total_discount += strata_discount
        grand_total = max(0, subtotal - total_discount)

        bonus_value = 0
        for b in bonus:
            sku_info = next((i for i in items if i['sku'] == b['sku']), None)
            if sku_info:
                bonus_value += b['qty'] * sku_info.get('unitPrice', 0)

        handler._send_json(200, {
            'purchased': [{'sku': i['sku'], 'name': i.get('name', ''), 'qty': i['qty'], 'unitPrice': i.get('unitPrice', 0), 'unitDiscount': i.get('unitDiscount', 0), 'lineTotal': i['qty'] * (i.get('unitPrice', 0) - i.get('unitDiscount', 0))} for i in purchased],
            'bonus': bonus,
            'subtotal': subtotal,
            'totalDiscount': total_discount,
            'strataDiscount': strata_discount,
            'grandTotal': grand_total,
            'bonusValue': bonus_value,
            'promosApplied': applied_promos
        })
    except Exception as e:
        write_log('ERROR', 'ordercalc', f'POST failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Create order
def do_orders_post(handler, data):
    user = handler._require_auth()
    if not user: return
    items = data.get('items', [])
    checkin_id = data.get('checkinId', '')
    store_uuid = data.get('storeUuid', '')
    place_name = data.get('storeName', '')
    grand_total = data.get('grandTotal', 0)
    promos = data.get('promosApplied', [])
    sales_channel = data.get('salesChannel', 'app')
    if not checkin_id or not items:
        return handler._send_json(400, {'error': 'checkinId dan items diperlukan'})
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()

        # Verify open check-in
        cur.execute("SELECT id, place_uuid FROM wim_visits WHERE id=%s AND user_id=%s AND checkout_at IS NULL", (checkin_id, user['id']))
        checkin = cur.fetchone()
        if not checkin:
            cur.close()
            ret_mysql(conn)
            return handler._send_json(400, {'error': 'Check-in tidak valid atau sudah selesai'})

        # Get driver UUID
        driver_uuid = user.get('driver_uuid', '')
        if not driver_uuid:
            cur.execute("SELECT driver_uuid FROM users WHERE id=%s", (user['id'],))
            u = cur.fetchone()
            if u: driver_uuid = str(u.get('driver_uuid') or '')

        # Create order UUID
        order_uuid = str(uuid_mod.uuid4())
        public_id = f"order_{order_uuid[:12].replace('-', 'x')}"

        # Create a payload row first (Fleetbase FK: orders.payload_uuid → payloads.uuid)
        payload_uuid = str(uuid_mod.uuid4())
        payload_pub = f"payload_{payload_uuid[:12].replace('-', 'x')}"
        cur.execute(
            "INSERT INTO payloads (uuid, public_id, company_uuid, meta, created_at, updated_at) "
            "VALUES (%s, %s, (SELECT company_uuid FROM users WHERE id=%s LIMIT 1), %s, NOW(), NOW())",
            (payload_uuid, payload_pub, user['id'],
             json.dumps({'store_uuid': store_uuid, 'store_name': place_name, 'source': 'wim-online'})))

        # Build order meta with items inline (no order_items table in Fleetbase)
        order_meta = json.dumps({
            'checkin_id': checkin_id,
            'store_uuid': store_uuid,
            'store_name': place_name or '',
            'sales_channel': sales_channel,
            'promos_applied': [{'promoRef': p.get('promoRef', ''), 'nama': p.get('nama', ''), 'jenis': p.get('jenis', '')} for p in promos],
            'grand_total': grand_total,
            'verification_status': 'pending',
            'verified_at': None,
            'source': 'wim-online',
            'items': [{
                'sku': i.get('sku', ''),
                'name': i.get('name', ''),
                'qty': i.get('qty', 0),
                'unit_price': i.get('unitPrice', 0),
                'unit_discount': i.get('unitDiscount', 0),
                'is_bonus': i.get('is_bonus', False),
                'promo_name': i.get('promoName', ''),
                'promo_ref': i.get('promoRef', '')
            } for i in items]
        })

        # Insert into Fleetbase orders table
        cur.execute(
            "INSERT INTO orders (uuid, public_id, company_uuid, driver_assigned_uuid, status, meta, created_at, updated_at, payload_uuid) "
            "VALUES (%s, %s, (SELECT company_uuid FROM users WHERE id=%s LIMIT 1), %s, 'pending', %s, NOW(), NOW(), %s)",
            (order_uuid, public_id, user['id'], driver_uuid or '', order_meta, payload_uuid))

# Items are stored inline in order_meta (no order_items table in Fleetbase)

        conn.commit()
        cur.close()
        ret_mysql(conn)

        write_log('INFO', 'orders', f'Order created: {public_id} by {user["email"]} for store {place_name} (Rp {grand_total})')
        handler._send_json(200, {
            'status': 'created',
            'orderId': public_id,
            'orderUuid': order_uuid,
            'grandTotal': grand_total,
            'verificationStatus': 'pending'
        })
    except Exception as e:
        write_log('ERROR', 'orders', f'POST failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Order history
def do_orders_get(handler):
    user = handler._require_auth()
    if not user: return
    qs = parse_qs(urlparse(handler.path).query)
    store_uuid = (qs.get('store_uuid') or [''])[0].strip()
    driver_uuid = user.get('driver_uuid', '')
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()
        where = "WHERE deleted_at IS NULL"
        params = []
        if driver_uuid:
            where += " AND driver_assigned_uuid=%s"
            params.append(driver_uuid)
        if store_uuid:
            where += " AND (JSON_UNQUOTE(JSON_EXTRACT(meta, '$.store_uuid'))=%s OR customer_uuid=%s)"
            params.extend([store_uuid, store_uuid])
        cur.execute(f"SELECT uuid, public_id, status, meta, created_at, updated_at FROM orders {where} ORDER BY created_at DESC LIMIT 50", params)
        orders = []
        for r in cur.fetchall():
            m = r['meta']
            if isinstance(m, str):
                try: m = json.loads(m)
                except: m = {}
            orders.append({
                'uuid': r['uuid'], 'orderId': r['public_id'], 'status': r['status'],
                'storeName': m.get('store_name', '') if isinstance(m, dict) else '',
                'grandTotal': m.get('grand_total', 0) if isinstance(m, dict) else 0,
                'verificationStatus': m.get('verification_status', '') if isinstance(m, dict) else '',
                'createdAt': str(r['created_at']) if r['created_at'] else '',
            })
        cur.close()
        ret_mysql(conn)
        handler._send_json(200, {'orders': orders})
    except Exception as e:
        write_log('ERROR', 'orders', f'GET failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Order detail
def do_order_detail(handler):
    user = handler._require_auth()
    if not user: return
    qs = parse_qs(urlparse(handler.path).query)
    order_uuid = (qs.get('uuid') or [''])[0].strip()
    if not order_uuid:
        return handler._send_json(400, {'error': 'uuid parameter required'})
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()
        cur.execute("SELECT uuid, public_id, status, meta, created_at FROM orders WHERE uuid=%s AND deleted_at IS NULL", (order_uuid,))
        order = cur.fetchone()
        if not order:
            cur.close()
            ret_mysql(conn)
            return handler._send_json(404, {'error': 'Order not found'})
        m = order['meta']
        if isinstance(m, str):
            try: m = json.loads(m)
            except: m = {}
        # Items are stored inline in order meta
        items = m.get('items', []) if isinstance(m, dict) else []
        cur.close()
        ret_mysql(conn)
        handler._send_json(200, {
            'uuid': order['uuid'], 'orderId': order['public_id'], 'status': order['status'],
            'storeName': m.get('store_name', '') if isinstance(m, dict) else '',
            'grandTotal': m.get('grand_total', 0) if isinstance(m, dict) else 0,
            'verificationStatus': m.get('verification_status', '') if isinstance(m, dict) else '',
            'createdAt': str(order['created_at']),
            'items': items
        })
    except Exception as e:
        write_log('ERROR', 'orders', f'DETAIL failed: {e}')
        handler._send_json(500, {'error': str(e)})

# ── Verify order (QR scan)
def do_order_verify(handler, data):
    user = handler._require_auth()
    if not user: return
    order_uuid = (data.get('orderUuid') or '').strip()
    if not order_uuid:
        return handler._send_json(400, {'error': 'orderUuid diperlukan'})
    try:
        conn = get_mysql()
        if not conn: return handler._send_json(500, {'error': 'DB connection failed'})
        cur = conn.cursor()
        cur.execute("SELECT uuid, public_id, meta, status FROM orders WHERE uuid=%s AND deleted_at IS NULL", (order_uuid,))
        order = cur.fetchone()
        if not order:
            cur.close()
            ret_mysql(conn)
            return handler._send_json(404, {'error': 'Order not found'})
        m = order['meta']
        if isinstance(m, str):
            try: m = json.loads(m)
            except: m = {}
        if isinstance(m, dict):
            m['verification_status'] = 'verified'
            m['verified_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("UPDATE orders SET meta=%s, status='verified' WHERE uuid=%s", (json.dumps(m) if isinstance(m, dict) else '{}', order_uuid))
        conn.commit()
        cur.close()
        ret_mysql(conn)
        write_log('INFO', 'orders', f'Order verified: {order["public_id"]} by {user["email"]}')
        handler._send_json(200, {'status': 'verified', 'orderId': order['public_id']})
    except Exception as e:
        write_log('ERROR', 'orders', f'VERIFY failed: {e}')
        handler._send_json(500, {'error': str(e)})