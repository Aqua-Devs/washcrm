import os
import json
import io
import base64
import datetime
import bcrypt
import jwt
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pressureflow-secret-key-change-me')

# Supabase client
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── AUTH HELPERS ───────────────────────────────────────────────
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '')
        if not token:
            return jsonify({'error': 'Token ontbreekt'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_role = data['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token verlopen'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Ongeldig token'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.user_role != 'admin':
            return jsonify({'error': 'Admin toegang vereist'}), 403
        return f(*args, **kwargs)
    return decorated

# ─── PAGES ──────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ─── AUTH ROUTES ────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    sb = get_supabase()
    hashed = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Check if any users exist (first user becomes admin)
    existing = sb.table('users').select('id').limit(1).execute()
    role = 'admin' if len(existing.data) == 0 else data.get('role', 'technician')
    
    try:
        result = sb.table('users').insert({
            'name': data['name'],
            'email': data['email'],
            'password_hash': hashed,
            'role': role
        }).execute()
        return jsonify({'message': 'Account aangemaakt', 'role': role}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    sb = get_supabase()
    
    try:
        result = sb.table('users').select('*').eq('email', data['email']).execute()
        if not result.data:
            return jsonify({'error': 'Ongeldige inloggegevens'}), 401
        
        user = result.data[0]
        if not bcrypt.checkpw(data['password'].encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({'error': 'Ongeldige inloggegevens'}), 401
        
        token = jwt.encode({
            'user_id': user['id'],
            'role': user['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role']}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── DASHBOARD ──────────────────────────────────────────────────
@app.route('/api/dashboard', methods=['GET'])
@token_required
def get_dashboard():
    sb = get_supabase()
    today = datetime.date.today().isoformat()
    
    # Get today's jobs
    today_jobs = sb.table('estimates').select('*, customers(name, address)').eq('status', 'akkoord').execute()
    
    # Get open quotes
    open_quotes = sb.table('estimates').select('id').eq('status', 'offerte').execute()
    
    # Revenue this month
    now = datetime.date.today()
    month_start = now.replace(day=1).isoformat()
    revenue = sb.table('estimates').select('total_incl_btw').in_('status', ['voltooid', 'factuur', 'betaald']).gte('updated_at', month_start).execute()
    month_revenue = sum(float(r['total_incl_btw']) for r in revenue.data)
    
    # Revenue last month
    last_month_end = now.replace(day=1) - datetime.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1).isoformat()
    last_revenue = sb.table('estimates').select('total_incl_btw').in_('status', ['voltooid', 'factuur', 'betaald']).gte('updated_at', last_month_start).lte('updated_at', last_month_end.isoformat()).execute()
    last_month_revenue = sum(float(r['total_incl_btw']) for r in last_revenue.data)
    
    # Inventory warnings
    inventory = sb.table('inventory').select('*').execute()
    warnings = [i for i in inventory.data if float(i['quantity_on_hand']) <= float(i['threshold_warning'])]
    
    # Customer count
    customers = sb.table('customers').select('id', count='exact').execute()
    
    result = {
        'today_jobs': today_jobs.data,
        'open_quotes_count': len(open_quotes.data),
        'month_revenue': month_revenue,
        'last_month_revenue': last_month_revenue,
        'inventory_warnings': warnings,
        'customer_count': customers.count or 0,
        'is_admin': request.user_role == 'admin'
    }
    
    return jsonify(result)

# ─── CUSTOMERS ──────────────────────────────────────────────────
@app.route('/api/customers', methods=['GET'])
@token_required
def get_customers():
    sb = get_supabase()
    search = request.args.get('search', '')
    query = sb.table('customers').select('*').order('created_at', desc=True)
    if search:
        query = query.or_(f'name.ilike.%{search}%,address.ilike.%{search}%,phone.ilike.%{search}%')
    result = query.execute()
    return jsonify(result.data)

@app.route('/api/customers', methods=['POST'])
@token_required
def create_customer():
    data = request.json
    sb = get_supabase()
    result = sb.table('customers').insert({
        'name': data['name'],
        'address': data.get('address', ''),
        'phone': data.get('phone', ''),
        'email': data.get('email', ''),
        'parking_situation': data.get('parking_situation', 'oprit'),
        'water_tap_location': data.get('water_tap_location', ''),
        'water_pressure_lpm': data.get('water_pressure_lpm', 0),
        'notes': data.get('notes', '')
    }).execute()
    return jsonify(result.data[0]), 201

@app.route('/api/customers/<customer_id>', methods=['GET'])
@token_required
def get_customer(customer_id):
    sb = get_supabase()
    result = sb.table('customers').select('*').eq('id', customer_id).execute()
    if not result.data:
        return jsonify({'error': 'Klant niet gevonden'}), 404
    # Get estimates for this customer
    estimates = sb.table('estimates').select('*').eq('customer_id', customer_id).order('created_at', desc=True).execute()
    customer = result.data[0]
    customer['estimates'] = estimates.data
    return jsonify(customer)

@app.route('/api/customers/<customer_id>', methods=['PUT'])
@token_required
def update_customer(customer_id):
    data = request.json
    sb = get_supabase()
    data['updated_at'] = datetime.datetime.utcnow().isoformat()
    result = sb.table('customers').update(data).eq('id', customer_id).execute()
    return jsonify(result.data[0])

@app.route('/api/customers/<customer_id>', methods=['DELETE'])
@token_required
def delete_customer(customer_id):
    sb = get_supabase()
    sb.table('customers').delete().eq('id', customer_id).execute()
    return jsonify({'message': 'Klant verwijderd'})

# ─── SERVICES ───────────────────────────────────────────────────
@app.route('/api/services', methods=['GET'])
@token_required
def get_services():
    sb = get_supabase()
    result = sb.table('services').select('*').eq('active', True).order('name').execute()
    return jsonify(result.data)

@app.route('/api/services', methods=['POST'])
@token_required
@admin_required
def create_service():
    data = request.json
    sb = get_supabase()
    result = sb.table('services').insert(data).execute()
    return jsonify(result.data[0]), 201

@app.route('/api/services/<service_id>', methods=['PUT'])
@token_required
@admin_required
def update_service(service_id):
    data = request.json
    sb = get_supabase()
    result = sb.table('services').update(data).eq('id', service_id).execute()
    return jsonify(result.data[0])

@app.route('/api/services/<service_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_service(service_id):
    sb = get_supabase()
    sb.table('services').update({'active': False}).eq('id', service_id).execute()
    return jsonify({'message': 'Dienst verwijderd'})

# ─── UPSELL ITEMS ──────────────────────────────────────────────
@app.route('/api/upsells', methods=['GET'])
@token_required
def get_upsells():
    sb = get_supabase()
    result = sb.table('upsell_items').select('*').eq('active', True).order('name').execute()
    return jsonify(result.data)

@app.route('/api/upsells', methods=['POST'])
@token_required
@admin_required
def create_upsell():
    data = request.json
    sb = get_supabase()
    result = sb.table('upsell_items').insert(data).execute()
    return jsonify(result.data[0]), 201

@app.route('/api/upsells/<upsell_id>', methods=['PUT'])
@token_required
@admin_required
def update_upsell(upsell_id):
    data = request.json
    sb = get_supabase()
    result = sb.table('upsell_items').update(data).eq('id', upsell_id).execute()
    return jsonify(result.data[0])

@app.route('/api/upsells/<upsell_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_upsell(upsell_id):
    sb = get_supabase()
    sb.table('upsell_items').update({'active': False}).eq('id', upsell_id).execute()
    return jsonify({'message': 'Upsell verwijderd'})

# ─── ESTIMATES ──────────────────────────────────────────────────
@app.route('/api/estimates', methods=['GET'])
@token_required
def get_estimates():
    sb = get_supabase()
    status = request.args.get('status', '')
    query = sb.table('estimates').select('*, customers(name, address, phone)').order('created_at', desc=True)
    if status:
        query = query.eq('status', status)
    result = query.execute()
    return jsonify(result.data)

@app.route('/api/estimates', methods=['POST'])
@token_required
def create_estimate():
    data = request.json
    sb = get_supabase()
    
    # Calculate totals
    subtotal = 0
    lines = data.get('lines', [])
    upsells = data.get('upsells', [])
    
    for line in lines:
        multiplier = float(line.get('multiplier', 1.0))
        line_total = float(line['square_meters']) * float(line['unit_price']) * multiplier
        line['line_total'] = line_total
        subtotal += line_total
    
    for upsell in upsells:
        subtotal += float(upsell['price'])
    
    btw_pct = float(data.get('btw_percentage', 21))
    btw_amount = subtotal * (btw_pct / 100)
    total_incl = subtotal + btw_amount
    
    # Create estimate
    estimate = sb.table('estimates').insert({
        'customer_id': data['customer_id'],
        'user_id': request.user_id,
        'status': data.get('status', 'concept'),
        'subtotal': subtotal,
        'btw_percentage': btw_pct,
        'total_incl_btw': total_incl,
        'notes': data.get('notes', '')
    }).execute()
    
    estimate_id = estimate.data[0]['id']
    
    # Insert lines
    for line in lines:
        sb.table('estimate_lines').insert({
            'estimate_id': estimate_id,
            'service_id': line.get('service_id'),
            'description': line['description'],
            'square_meters': line['square_meters'],
            'pollution_level': line.get('pollution_level', 'standaard'),
            'unit_price': line['unit_price'],
            'multiplier': line.get('multiplier', 1.0),
            'line_total': line['line_total']
        }).execute()
    
    # Insert upsells
    for upsell in upsells:
        sb.table('estimate_upsells').insert({
            'estimate_id': estimate_id,
            'upsell_item_id': upsell.get('upsell_item_id'),
            'description': upsell['description'],
            'price': upsell['price']
        }).execute()
    
    return jsonify(estimate.data[0]), 201

@app.route('/api/estimates/<estimate_id>', methods=['GET'])
@token_required
def get_estimate(estimate_id):
    sb = get_supabase()
    estimate = sb.table('estimates').select('*, customers(*)').eq('id', estimate_id).execute()
    if not estimate.data:
        return jsonify({'error': 'Offerte niet gevonden'}), 404
    
    lines = sb.table('estimate_lines').select('*').eq('estimate_id', estimate_id).execute()
    upsells = sb.table('estimate_upsells').select('*').eq('estimate_id', estimate_id).execute()
    photos = sb.table('project_photos').select('id, photo_type, caption, created_at').eq('estimate_id', estimate_id).execute()
    
    result = estimate.data[0]
    result['lines'] = lines.data
    result['upsells'] = upsells.data
    result['photos'] = photos.data
    return jsonify(result)

@app.route('/api/estimates/<estimate_id>', methods=['PUT'])
@token_required
def update_estimate(estimate_id):
    data = request.json
    sb = get_supabase()
    
    update_data = {k: v for k, v in data.items() if k in [
        'status', 'subtotal', 'btw_percentage', 'total_incl_btw', 'signature_data', 'notes'
    ]}
    update_data['updated_at'] = datetime.datetime.utcnow().isoformat()
    
    result = sb.table('estimates').update(update_data).eq('id', estimate_id).execute()
    return jsonify(result.data[0])

@app.route('/api/estimates/<estimate_id>/sign', methods=['POST'])
@token_required
def sign_estimate(estimate_id):
    data = request.json
    sb = get_supabase()
    sb.table('estimates').update({
        'signature_data': data['signature'],
        'status': 'akkoord',
        'updated_at': datetime.datetime.utcnow().isoformat()
    }).eq('id', estimate_id).execute()
    return jsonify({'message': 'Offerte getekend en geaccepteerd'})

@app.route('/api/estimates/<estimate_id>/complete', methods=['POST'])
@token_required
def complete_estimate(estimate_id):
    sb = get_supabase()
    
    # Get estimate lines
    lines = sb.table('estimate_lines').select('*, services(linked_inventory_id, chemical_usage_rate)').eq('estimate_id', estimate_id).execute()
    
    # Auto-deduct inventory
    for line in lines.data:
        service = line.get('services')
        if service and service.get('linked_inventory_id') and service.get('chemical_usage_rate'):
            usage = float(line['square_meters']) * float(service['chemical_usage_rate'])
            inv_id = service['linked_inventory_id']
            
            # Get current stock
            inv = sb.table('inventory').select('quantity_on_hand').eq('id', inv_id).execute()
            if inv.data:
                new_qty = max(0, float(inv.data[0]['quantity_on_hand']) - usage)
                sb.table('inventory').update({
                    'quantity_on_hand': new_qty,
                    'updated_at': datetime.datetime.utcnow().isoformat()
                }).eq('id', inv_id).execute()
                
                # Log the change
                sb.table('inventory_log').insert({
                    'inventory_id': inv_id,
                    'estimate_id': estimate_id,
                    'change_amount': -usage,
                    'reason': f'Auto-aftrek klus voltooid ({line["square_meters"]} m²)'
                }).execute()
    
    # Update status
    sb.table('estimates').update({
        'status': 'voltooid',
        'updated_at': datetime.datetime.utcnow().isoformat()
    }).eq('id', estimate_id).execute()
    
    return jsonify({'message': 'Klus voltooid, voorraad bijgewerkt'})

# ─── PHOTOS ─────────────────────────────────────────────────────
@app.route('/api/estimates/<estimate_id>/photos', methods=['POST'])
@token_required
def upload_photo(estimate_id):
    data = request.json
    sb = get_supabase()
    
    result = sb.table('project_photos').insert({
        'estimate_id': estimate_id,
        'customer_id': data.get('customer_id'),
        'photo_type': data.get('photo_type', 'voor'),
        'photo_data': data['photo_data'],
        'caption': data.get('caption', '')
    }).execute()
    
    return jsonify({'id': result.data[0]['id']}), 201

@app.route('/api/photos/<photo_id>', methods=['GET'])
@token_required
def get_photo(photo_id):
    sb = get_supabase()
    result = sb.table('project_photos').select('*').eq('id', photo_id).execute()
    if not result.data:
        return jsonify({'error': 'Foto niet gevonden'}), 404
    return jsonify(result.data[0])

@app.route('/api/photos/<photo_id>', methods=['DELETE'])
@token_required
def delete_photo(photo_id):
    sb = get_supabase()
    sb.table('project_photos').delete().eq('id', photo_id).execute()
    return jsonify({'message': 'Foto verwijderd'})

# ─── INVENTORY ──────────────────────────────────────────────────
@app.route('/api/inventory', methods=['GET'])
@token_required
def get_inventory():
    sb = get_supabase()
    result = sb.table('inventory').select('*').order('item_name').execute()
    return jsonify(result.data)

@app.route('/api/inventory', methods=['POST'])
@token_required
@admin_required
def create_inventory_item():
    data = request.json
    sb = get_supabase()
    result = sb.table('inventory').insert(data).execute()
    return jsonify(result.data[0]), 201

@app.route('/api/inventory/<item_id>', methods=['PUT'])
@token_required
@admin_required
def update_inventory(item_id):
    data = request.json
    sb = get_supabase()
    data['updated_at'] = datetime.datetime.utcnow().isoformat()
    result = sb.table('inventory').update(data).eq('id', item_id).execute()
    return jsonify(result.data[0])

@app.route('/api/inventory/<item_id>/adjust', methods=['POST'])
@token_required
def adjust_inventory(item_id):
    data = request.json
    sb = get_supabase()
    
    current = sb.table('inventory').select('quantity_on_hand').eq('id', item_id).execute()
    if not current.data:
        return jsonify({'error': 'Item niet gevonden'}), 404
    
    new_qty = float(current.data[0]['quantity_on_hand']) + float(data['amount'])
    sb.table('inventory').update({
        'quantity_on_hand': max(0, new_qty),
        'updated_at': datetime.datetime.utcnow().isoformat()
    }).eq('id', item_id).execute()
    
    sb.table('inventory_log').insert({
        'inventory_id': item_id,
        'change_amount': data['amount'],
        'reason': data.get('reason', 'Handmatige aanpassing')
    }).execute()
    
    return jsonify({'message': 'Voorraad aangepast', 'new_quantity': new_qty})

# ─── SETTINGS ───────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
@token_required
def get_settings():
    sb = get_supabase()
    result = sb.table('settings').select('*').execute()
    settings = {s['key']: s['value'] for s in result.data}
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
@token_required
@admin_required
def update_settings():
    data = request.json
    sb = get_supabase()
    for key, value in data.items():
        sb.table('settings').upsert({
            'key': key,
            'value': str(value),
            'updated_at': datetime.datetime.utcnow().isoformat()
        }).execute()
    return jsonify({'message': 'Instellingen opgeslagen'})

# ─── PDF GENERATION ─────────────────────────────────────────────
@app.route('/api/estimates/<estimate_id>/pdf', methods=['GET'])
@token_required
def generate_pdf(estimate_id):
    sb = get_supabase()
    
    # Fetch all data
    estimate = sb.table('estimates').select('*, customers(*)').eq('id', estimate_id).execute()
    if not estimate.data:
        return jsonify({'error': 'Offerte niet gevonden'}), 404
    
    est = estimate.data[0]
    customer = est.get('customers', {})
    lines = sb.table('estimate_lines').select('*').eq('estimate_id', estimate_id).execute()
    upsells = sb.table('estimate_upsells').select('*').eq('estimate_id', estimate_id).execute()
    settings_data = sb.table('settings').select('*').execute()
    settings = {s['key']: s['value'] for s in settings_data.data}
    
    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CompanyName', fontSize=20, spaceAfter=6, textColor=HexColor('#1a56db'), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='DocTitle', fontSize=14, spaceAfter=12, textColor=HexColor('#374151'), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='SectionHead', fontSize=11, spaceAfter=6, textColor=HexColor('#1a56db'), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='BodyText2', fontSize=10, spaceAfter=4, textColor=HexColor('#374151')))
    styles.add(ParagraphStyle(name='SmallRight', fontSize=9, alignment=TA_RIGHT, textColor=HexColor('#6b7280')))
    styles.add(ParagraphStyle(name='TotalStyle', fontSize=13, fontName='Helvetica-Bold', textColor=HexColor('#1a56db'), alignment=TA_RIGHT))
    
    story = []
    
    # Header
    is_invoice = est['status'] in ['factuur', 'betaald']
    doc_type = 'FACTUUR' if is_invoice else 'OFFERTE'
    prefix = settings.get('invoice_prefix', 'FAC') if is_invoice else settings.get('estimate_prefix', 'OFF')
    
    story.append(Paragraph(settings.get('company_name', 'PressureFlow'), styles['CompanyName']))
    if settings.get('company_address'):
        story.append(Paragraph(settings['company_address'], styles['BodyText2']))
    if settings.get('company_phone'):
        story.append(Paragraph(f"Tel: {settings['company_phone']}", styles['BodyText2']))
    if settings.get('company_email'):
        story.append(Paragraph(f"E-mail: {settings['company_email']}", styles['BodyText2']))
    if settings.get('company_kvk'):
        story.append(Paragraph(f"KVK: {settings['company_kvk']}", styles['BodyText2']))
    if settings.get('company_btw_id'):
        story.append(Paragraph(f"BTW-ID: {settings['company_btw_id']}", styles['BodyText2']))
    
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(f"{doc_type} {prefix}-{estimate_id[:8].upper()}", styles['DocTitle']))
    story.append(Paragraph(f"Datum: {est['created_at'][:10]}", styles['BodyText2']))
    story.append(Spacer(1, 0.5*cm))
    
    # Customer info
    story.append(Paragraph('KLANTGEGEVENS', styles['SectionHead']))
    story.append(Paragraph(f"{customer.get('name', '-')}", styles['BodyText2']))
    if customer.get('address'):
        story.append(Paragraph(customer['address'], styles['BodyText2']))
    if customer.get('phone'):
        story.append(Paragraph(f"Tel: {customer['phone']}", styles['BodyText2']))
    if customer.get('email'):
        story.append(Paragraph(f"E-mail: {customer['email']}", styles['BodyText2']))
    
    story.append(Spacer(1, 0.8*cm))
    
    # Services table
    story.append(Paragraph('WERKZAAMHEDEN', styles['SectionHead']))
    table_data = [['Omschrijving', 'm²', 'Prijs/m²', 'Vervuiling', 'Totaal']]
    for line in lines.data:
        pollution = 'Zwaar (1.3x)' if line['pollution_level'] == 'zwaar' else 'Standaard'
        table_data.append([
            line['description'],
            f"{float(line['square_meters']):.1f}",
            f"€{float(line['unit_price']):.2f}",
            pollution,
            f"€{float(line['line_total']):.2f}"
        ])
    
    if upsells.data:
        for ups in upsells.data:
            table_data.append([ups['description'], '', '', '', f"€{float(ups['price']):.2f}"])
    
    t = Table(table_data, colWidths=[7*cm, 2*cm, 2.5*cm, 2.5*cm, 3*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f9fafb')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    
    # Totals
    btw_pct = float(est['btw_percentage'])
    subtotal = float(est['subtotal'])
    btw_amount = subtotal * (btw_pct / 100)
    
    story.append(Paragraph(f"Subtotaal: €{subtotal:.2f}", styles['SmallRight']))
    story.append(Paragraph(f"BTW ({btw_pct:.0f}%): €{btw_amount:.2f}", styles['SmallRight']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"TOTAAL: €{float(est['total_incl_btw']):.2f}", styles['TotalStyle']))
    
    # Signature
    if est.get('signature_data'):
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph('HANDTEKENING KLANT', styles['SectionHead']))
        try:
            sig_data = est['signature_data'].split(',')[1] if ',' in est['signature_data'] else est['signature_data']
            sig_bytes = base64.b64decode(sig_data)
            sig_buffer = io.BytesIO(sig_bytes)
            sig_img = RLImage(sig_buffer, width=6*cm, height=3*cm)
            story.append(sig_img)
        except Exception:
            story.append(Paragraph('[Handtekening opgeslagen]', styles['BodyText2']))
    
    # Payment info for invoices
    if is_invoice and settings.get('company_iban'):
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph('BETAALGEGEVENS', styles['SectionHead']))
        story.append(Paragraph(f"IBAN: {settings['company_iban']}", styles['BodyText2']))
        story.append(Paragraph(f"T.n.v. {settings.get('company_name', '')}", styles['BodyText2']))
        story.append(Paragraph(f"Ref: {prefix}-{estimate_id[:8].upper()}", styles['BodyText2']))
    
    if est.get('notes'):
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph('OPMERKINGEN', styles['SectionHead']))
        story.append(Paragraph(est['notes'], styles['BodyText2']))
    
    doc.build(story)
    buffer.seek(0)
    
    filename = f"{doc_type.lower()}_{estimate_id[:8]}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

# ─── USERS (Admin) ─────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@token_required
@admin_required
def get_users():
    sb = get_supabase()
    result = sb.table('users').select('id, name, email, role, created_at').order('created_at').execute()
    return jsonify(result.data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
