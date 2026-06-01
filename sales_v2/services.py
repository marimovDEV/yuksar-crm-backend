from django.db import transaction
from django.utils import timezone
from .models import Invoice, SaleItem, Customer
from inventory.models import InventoryBatch
from warehouse_v2.models import Warehouse, Material
from rest_framework.exceptions import ValidationError
from finance_v2.models import FinancialTransaction, Cashbox, ClientBalance
from accounting.signals import _safe_create_entry
from decimal import Decimal
from finance.services import record_double_entry


def _release_reserved_inventory(item):
    if not item.source_warehouse_id or not item.batch_number:
        return

    inv = InventoryBatch.objects.select_for_update().filter(
        product=item.product,
        location_id=item.source_warehouse_id,
        batch_number=item.batch_number,
    ).first()
    if not inv:
        return

    inv.reserved_weight = max(float(inv.reserved_weight) - float(item.quantity), 0)
    inv.save(update_fields=['reserved_weight'])


def _ensure_sales_document(invoice, warehouse, items, user=None):
    """
    Every sales invoice must have a backing business document.
    """
    from documents.models import Document, DocumentItem

    doc, _ = Document.objects.get_or_create(
        type='HISOB_FAKTURA_CHIQIM',
        number=invoice.invoice_number,
        defaults={
            'status': 'CREATED',
            'client': invoice.customer,
            'from_warehouse': warehouse,
            'created_by': user or invoice.created_by,
            'total_amount': invoice.total_amount,
            'currency': 'UZS',
            'invoice_date': invoice.date.date() if invoice.date else timezone.now().date(),
        },
    )

    if not doc.items.exists():
        for item in items:
            product = Material.objects.get(id=item['product_id'])
            DocumentItem.objects.create(
                document=doc,
                product=product,
                quantity=float(item['quantity']),
                price_at_moment=float(item['price']),
                batch_number=item.get('batch_number'),
            )
    return doc


def _ensure_waybill_document(invoice, user=None):
    from documents.models import Document, DocumentItem

    waybill_number = f"WB-{invoice.invoice_number}"
    doc, _ = Document.objects.get_or_create(
        type='ICHKI_YUK_XATI',
        number=waybill_number,
        defaults={
            'status': 'CREATED',
            'client': invoice.customer,
            'created_by': user or invoice.created_by,
        },
    )
    if not doc.items.exists():
        for item in invoice.items.all():
            DocumentItem.objects.create(
                document=doc,
                product=item.product,
                quantity=item.quantity,
                price_at_moment=item.price,
                batch_number=item.batch_number,
            )
    return doc

def create_invoice(warehouse_id, customer_id, items, payment_method='CASH', delivery_address='', notes='', discount_amount=0, created_by=None):
    """
    Creates a NEW order (invoice) and reserves stock.
    items: list of {'product_id': int, 'quantity': float, 'price': float, 'batch_number': str}
    """
    warehouse = Warehouse.objects.get(id=warehouse_id)
    customer = Customer.objects.get(id=customer_id)
    if not items:
        raise ValidationError("Kamida bitta mahsulot bo'lishi kerak.")
    
    # Use ORD- format as per user request
    last_order = Invoice.objects.filter(invoice_number__startswith='ORD-').order_by('-id').first()
    if last_order:
        try:
            last_num = int(last_order.invoice_number.split('-')[1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    invoice_number = f"ORD-{str(new_num).zfill(4)}"

    with transaction.atomic():
        # Phase 6: Credit Limit Guard
        from finance_v2.models import ClientBalance
        cb, _ = ClientBalance.objects.get_or_create(customer=customer)
        current_debt = float(cb.total_debt)
        
        # Phase 6: Dynamic Pricing (VIP Suggestion)
        if customer.segment == 'VIP' and float(discount_amount or 0) == 0:
            # We don't know total_amount yet, so we will apply it after calculating items
            pass 
        
        invoice = Invoice.objects.create(
            invoice_number=invoice_number,
            customer=customer,
            status='NEW',
            payment_method=payment_method,
            delivery_address=delivery_address,
            notes=notes,
            discount_amount=discount_amount,
            created_by=created_by
        )

        total_amount = 0
        for item in items:
            product = Material.objects.get(id=item['product_id'])
            qty = float(item['quantity'])
            price = float(item['price'])
            batch = item.get('batch_number')
            if qty <= 0:
                raise ValidationError(f"{product.name} uchun miqdor 0 dan katta bo'lishi kerak.")
            if price < 0:
                raise ValidationError(f"{product.name} uchun narx manfiy bo'lishi mumkin emas.")

            # 1. Handle Reservation if batch is provided
            if batch:
                inv, created = InventoryBatch.objects.select_for_update().get_or_create(
                    product=product,
                    location=warehouse,
                    batch_number=batch,
                    defaults={'initial_weight': 0, 'current_weight': 0}
                )
                
                available = float(inv.current_weight) - float(inv.reserved_weight)
                if available < qty:
                    raise ValidationError(
                        f"Yetersiz qoldiq: {product.name} ({batch}). "
                        f"Mavjud: {inv.current_weight}, Bandda: {inv.reserved_weight}, So'ralgan: {qty}"
                    )
                
                inv.reserved_weight = float(inv.reserved_weight) + qty
                inv.save()

            # 2. Find and Link Batch (FIFO Locking)
            prod_batch = None
            raw_batch = None
            if batch:
                from production_v2.models import ProductionBatch
                from warehouse_v2.models import RawMaterialBatch
                prod_batch = ProductionBatch.objects.filter(batch_number=batch).first()
                if not prod_batch:
                    raw_batch = RawMaterialBatch.objects.filter(batch_number=batch).first()

            # 3. Create Sale Item
            SaleItem.objects.create(
                invoice=invoice,
                product=product,
                source_warehouse=warehouse,
                batch_number=batch,
                production_batch=prod_batch,
                raw_material_batch=raw_batch,
                quantity=qty,
                price=price
            )
            total_amount += (qty * price)

        discount_amount = float(discount_amount or 0)
        if discount_amount < 0:
            raise ValidationError("Chegirma manfiy bo'lishi mumkin emas.")
        if discount_amount > total_amount:
            raise ValidationError("Chegirma umumiy summadan katta bo'lishi mumkin emas.")

        # Phase 6: VIP Auto-Discount (10%)
        if customer.segment == 'VIP' and discount_amount == 0:
            discount_amount = total_amount * 0.10
        
        invoice.total_amount = total_amount - discount_amount
        invoice.discount_amount = discount_amount
        invoice.save()

        # Phase 6: Post-Invoice Credit Limit Validation
        if payment_method == 'DEBT':
            new_total_debt = current_debt + float(invoice.total_amount)
            if customer.credit_limit > 0 and new_total_debt > float(customer.credit_limit):
                raise ValidationError(
                    f"Kredit limiti oshib ketdi! Mijoz limiti: {customer.credit_limit:,.0f} UZS. "
                    f"Hozirgi qarz: {current_debt:,.0f} UZS. "
                    f"Yangi buyurtma: {invoice.total_amount:,.0f} UZS. "
                )

        _ensure_sales_document(invoice, warehouse, items, user=created_by)

    return invoice

def update_customer_intelligence(customer_id):
    """Refreshes CRM metrics and segmentation (Phase 6)."""
    from .models import Customer, Invoice
    from finance_v2.models import ClientBalance
    from django.db.models import Sum, Avg
    
    customer = Customer.objects.get(id=customer_id)
    invoices = Invoice.objects.filter(customer=customer, status='COMPLETED')
    
    total_rev = invoices.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    customer.total_revenue = total_rev
    customer.order_count = invoices.count()
    customer.avg_order_value = invoices.aggregate(Avg('total_amount'))['total_amount__avg'] or 0
    
    last_inv = invoices.order_by('-date').first()
    if last_inv:
        customer.last_purchase_date = last_inv.date
        
    # VIP Threshold: 100M UZS
    if total_rev >= 100000000:
        customer.segment = 'VIP'
    
    cb, _ = ClientBalance.objects.get_or_create(customer=customer)
    if cb.overdue_debt > 0:
        customer.segment = 'RISK'
        customer.debt_status = 'OVERDUE'
    else:
        customer.debt_status = 'HEALTHY'
        if customer.segment != 'VIP':
            customer.segment = 'REGULAR'
            
    customer.save()

def transition_invoice_status(invoice_id, new_status, performed_by=None):
    """
    Handles state transitions for an order with FULL AUTOMATION.
    
    Flow: NEW → CONFIRMED → (IN_PRODUCTION if no stock) → READY → SHIPPED → EN_ROUTE → DELIVERED → COMPLETED
    """
    from inventory.services import get_stock_balance
    from warehouse_v2.models import Warehouse
    from .models import Delivery

    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(id=invoice_id)
        old_status = invoice.status
        
        if old_status == new_status:
            return invoice

        # CRM Intelligence Trigger (Phase 6)
        if new_status == 'COMPLETED':
            update_customer_intelligence(invoice.customer.id)
            
        # ── CONFIRMED: Auto-check stock, create ProductionOrder if needed ──
        if new_status == 'CONFIRMED':
            sklad4 = Warehouse.objects.filter(name__icontains='Sklad №4').first()
            needs_production = False

            for item in invoice.items.all():
                available = 0
                if sklad4:
                    available = get_stock_balance(item.product, sklad4)
                
                if float(available) < float(item.quantity):
                    # Not enough stock → auto-create production order
                    shortfall = float(item.quantity) - float(available)
                    try:
                        create_production_order_from_sale(
                            invoice_id=invoice.id,
                            product_id=item.product.id,
                            quantity=int(shortfall),
                            priority='HIGH',
                            responsible=performed_by
                        )
                    except Exception:
                        pass  # Production order may already exist
                    needs_production = True

            if needs_production:
                invoice.status = 'IN_PRODUCTION'
            else:
                invoice.status = 'CONFIRMED'
            invoice.save()
            return invoice

        # ── READY: Production completed, stock available ──
        elif new_status == 'READY':
            invoice.status = 'READY'
            invoice.save()
            return invoice

        # ── SHIPPED: Deduct stock + auto-create Delivery for Courier ──
        elif new_status == 'SHIPPED':
            if old_status not in ['NEW', 'CONFIRMED', 'READY']:
                raise ValidationError("Faqat tayyor buyurtmalarni jo'natish mumkin.")
            
            sklad4 = Warehouse.objects.filter(name__icontains='Sklad №4').first()

            for item in invoice.items.all():
                # Deduct from Sklad 4
                source_warehouse = item.source_warehouse or sklad4
                if source_warehouse:
                    from inventory.services import update_inventory as inv_update
                    inv_update(
                        item.product,
                        source_warehouse,
                        -item.quantity,
                        batch_number=item.batch_number
                    )

                # Release reservation if any
                _release_reserved_inventory(item)

            # Auto-create Delivery for Courier
            if not hasattr(invoice, 'delivery') or not invoice.delivery:
                try:
                    Delivery.objects.create(
                        invoice=invoice,
                        status='PENDING'
                    )
                except Exception:
                    pass  # Delivery may already exist (OneToOne)

            _ensure_waybill_document(invoice, user=performed_by)
            _finalize_profitability_and_cogs(invoice, user=performed_by)

        # ── EN_ROUTE: Courier picked up ──
        elif new_status == 'EN_ROUTE':
            try:
                delivery = invoice.delivery
                delivery.status = 'EN_ROUTE'
                delivery.started_at = timezone.now()
                if performed_by:
                    delivery.courier = performed_by
                delivery.save()
            except Exception:
                pass

        # ── DELIVERED: Courier delivered ──
        elif new_status == 'DELIVERED':
            try:
                delivery = invoice.delivery
                delivery.status = 'DELIVERED'
                delivery.delivered_at = timezone.now()
                delivery.save()
            except Exception:
                pass

        # ── COMPLETED: Handle Finance ──
        elif new_status == 'COMPLETED':
            if invoice.payment_method == 'DEBT':
                cb, _ = ClientBalance.objects.get_or_create(customer=invoice.customer)
                cb.total_debt += invoice.total_amount
                cb.save()
                
                # Finance: Accounts Receivable (4010) -> Revenue (9010)
                record_double_entry(
                    description=f"Sotuv (Qarz) #{invoice.invoice_number}",
                    entries=[
                        {'account_code': '4010', 'debit': invoice.total_amount, 'credit': 0},
                        {'account_code': '9010', 'debit': 0, 'credit': invoice.total_amount},
                    ],
                    reference=invoice.invoice_number,
                    user=performed_by
                )
            else:
                cashbox_type = 'CASH' if invoice.payment_method == 'CASH' else ('BANK' if invoice.payment_method == 'BANK' else 'CARD')
                cashbox = Cashbox.objects.filter(type=cashbox_type, is_active=True).first()
                if cashbox:
                    FinancialTransaction.objects.create(
                        cashbox=cashbox,
                        amount=invoice.total_amount,
                        type='INCOME',
                        customer=invoice.customer,
                        description=f"Sotuv #{invoice.invoice_number} uchun to'lov",
                        performed_by=performed_by
                    )
                    
                    # Finance: Cash/Bank (1010/1020) -> Revenue (9010)
                    acc_code = '1010' if cashbox_type == 'CASH' else '1020'
                    record_double_entry(
                        description=f"Sotuv (Naqd/Bank) #{invoice.invoice_number}",
                        entries=[
                            {'account_code': acc_code, 'debit': invoice.total_amount, 'credit': 0},
                            {'account_code': '9010', 'debit': 0, 'credit': invoice.total_amount},
                        ],
                        reference=invoice.invoice_number,
                        user=performed_by
                    )
                else:
                    raise ValidationError("Mos aktiv kassa topilmadi.")

        # ── CANCELLED: Release Reservation ──
        elif new_status == 'CANCELLED':
            if old_status in ['NEW', 'CONFIRMED', 'READY']:
                for item in invoice.items.all():
                    _release_reserved_inventory(item)

        invoice.status = new_status
        invoice.save()

    return invoice

def create_production_order_from_sale(invoice_id, product_id, quantity, priority='MEDIUM', responsible=None):
    """
    Creates a ProductionOrder linked to a sales invoice (MTO).
    """
    from production_v2.models import ProductionOrder
    from warehouse_v2.models import Material
    
    invoice = Invoice.objects.get(id=invoice_id)
    product = Material.objects.get(id=product_id)
    
    from production_v2.services import create_production_order
    
    # Check if already exists to avoid duplicates
    if invoice.production_order_id:
        return ProductionOrder.objects.get(id=invoice.production_order_id)
        
    p_order = create_production_order(
        product=product,
        quantity=quantity,
        order_number=f"PROD-{invoice.invoice_number}",
        user=responsible,
        source=invoice.invoice_number,
        priority=priority
    )
    
    invoice.production_order_id = p_order.id
    invoice.save()
    return p_order

def _finalize_profitability_and_cogs(invoice, user=None):
    """
    Finalizes profit calculation and records COGS at SHIPPED status.
    Enterprise Level: DR 9110 / CR 2810.
    """
    total_profit = Decimal(0)
    total_revenue = Decimal(0)
    
    for item in invoice.items.all():
        cost_per_unit = Decimal(0)
        
        # 1. Determine unit cost (Batch FIFO vs AVG Legacy)
        if item.production_batch:
            cost_per_unit = item.production_batch.unit_cost
        elif item.raw_material_batch:
            cost_per_unit = item.raw_material_batch.price_per_unit
        else:
            # Fallback to standard price (Legacy)
            cost_per_unit = item.product.price
            item.is_legacy = True
            
        item.cost_price = cost_per_unit
        revenue = Decimal(str(item.price)) * Decimal(str(item.quantity))
        item.profit = revenue - (cost_per_unit * Decimal(str(item.quantity)))
        
        if revenue > 0:
            item.margin_percent = float((item.profit / revenue) * 100)
        else:
            item.margin_percent = -100 if item.profit < 0 else 0
            
        item.save()
        total_profit += item.profit
        total_revenue += revenue
        
        # 2. Record COGS Journal Entry
        cogs_amount = cost_per_unit * Decimal(str(item.quantity))
        if cogs_amount > 0:
            # DR: 9110 (Sotuv tannarxi)  CR: 2810 (Tayyor mahsulot) or 1010
            # Standard logic: categorize by product type
            inv_acc = '2810' if item.product.category == 'FINISHED' else '1010'
            _safe_create_entry(
                description=f"COGS: {invoice.invoice_number} - {item.product.name} (Qty: {item.quantity})",
                lines=[
                    {'account_code': '9110', 'debit': cogs_amount, 'credit': 0, 'description': "Sotilgan mahsulot tannarxi"},
                    {'account_code': inv_acc, 'debit': 0, 'credit': cogs_amount, 'description': f"Zahirani hisobdan chiqarish: {item.product.name}"},
                ],
                source_type='SALE',
                source_id=invoice.id,
                source_description=f"COGS for {invoice.invoice_number}",
                user=user
            )

    invoice.total_profit = total_profit
    if total_revenue > 0:
        invoice.avg_margin_percent = float((total_profit / total_revenue) * 100)
    invoice.save(update_fields=['total_profit', 'avg_margin_percent'])

def create_contact_log(customer_id, manager, contact_type, notes, follow_up_date=None):
    """
    Creates a new contact log for CRM.
    """
    from .models import ContactLog
    log = ContactLog.objects.create(
        customer_id=customer_id,
        manager=manager,
        contact_type=contact_type,
        notes=notes,
        follow_up_date=follow_up_date
    )
    return log
