from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Branch, ProductCatalog, BranchProduct, Order, OrderItem, Payment, StockTransaction, Supplier, PurchaseOrder, PurchaseOrderItem, Quotation, QuotationItem, SubCategory, Expense, ExpenseV2, ExpensePayment, Delivery, DeliveryPayment
from datetime import datetime, timedelta
import os
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from functools import wraps
from decimal import Decimal
import cloudinary
import cloudinary.uploader
import cloudinary.api
app = Flask(__name__)

# Cloudinary Configuration
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dxyewzvnr')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '171127627627327')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'zgKkOpX35l93D7CdwnWOWGF2mk8')

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# Cloudinary helper functions
def upload_to_cloudinary(file, folder="expense_receipts"):
    """Upload file to Cloudinary and return the secure URL"""
    try:
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="auto",  # Automatically detect image, video, or raw
            quality="auto:good",   # Optimize quality
            fetch_format="auto"    # Auto format based on browser
        )
        return result.get('secure_url')
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def delete_from_cloudinary(public_id):
    """Delete file from Cloudinary using public ID"""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get('result') == 'ok'
    except Exception as e:
        print(f"Cloudinary delete error: {e}")
        return False

# Branch access control helper functions
def get_user_accessible_branch_ids():
    """Get list of branch IDs the current user has access to"""
    if not current_user.is_authenticated:
        return []
    
    if current_user.has_all_branch_access():
        # User has access to all branches - return all branch IDs
        return [branch.id for branch in Branch.query.all()]
    else:
        # User has limited access - return their accessible branch IDs
        return current_user.accessible_branch_ids or []

def filter_by_user_branches(query, branch_field):
    """Filter a query by user's accessible branches"""
    accessible_branch_ids = get_user_accessible_branch_ids()
    if accessible_branch_ids:
        return query.filter(branch_field.in_(accessible_branch_ids))
    else:
        # If user has no branch access, return empty query
        return query.filter(False)

def get_user_accessible_branches():
    """Get Branch objects for user's accessible branches"""
    if not current_user.is_authenticated:
        return []
    return current_user.get_accessible_branches()
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a secure secret key
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:deno0707@localhost:5432/abzone'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:#Deno0707@69.197.187.23:5432/abzone'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Custom Jinja2 filters
@app.template_filter('east_africa_time')
def east_africa_time(dt):
    """Convert UTC time to East Africa Time (+3 hours)"""
    if dt is None:
        return None
    return dt + timedelta(hours=3)

@app.template_filter('strftime')
def strftime_filter(dt, format_string):
    """Format datetime objects using strftime"""
    if dt is None:
        return None
    try:
        return dt.strftime(format_string)
    except (AttributeError, ValueError):
        return str(dt)

@login_manager.unauthorized_handler
def unauthorized():
    flash('Please log in to access this page.', 'error')
    return redirect(url_for('login'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def check_user_role():
    """Check user role on every request for additional security"""
    if current_user.is_authenticated:
        if current_user.role != 'cashier':
            flash('Access denied. Only cashiers can access this application.', 'error')
            logout_user()
            return redirect(url_for('login'))

def cashier_required(f):
    """Decorator to ensure only users with 'cashier' role can access the route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'cashier':
            flash('Access denied. Only cashiers can access this application.', 'error')
            logout_user()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
print('Creating database tables...')
with app.app_context():
    db.create_all()
    print('✅ Database tables created successfully!')
# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        # Check if user has cashier role
        if current_user.role != 'cashier':
            flash('Access denied. Only cashiers can access this application.', 'error')
            logout_user()
            return redirect(url_for('login'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            # Check if user has cashier role
            if user.role != 'cashier':
                flash('Access denied. Only cashiers can access this application.', 'error')
                return render_template('login.html')
            
            login_user(user)
            flash(f'Welcome back, {user.firstname}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@cashier_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@cashier_required
def dashboard():
    from datetime import datetime, date
    from sqlalchemy import func
    
    # Get today's date
    today = date.today()
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get pending orders count (filtered by accessible branches)
    pending_orders_query = Order.query.filter_by(approvalstatus=False)
    if accessible_branch_ids:
        pending_orders_query = pending_orders_query.filter(Order.branchid.in_(accessible_branch_ids))
    pending_orders_count = pending_orders_query.count()
    
    # Get today's orders count (filtered by accessible branches)
    today_orders_query = Order.query.filter(func.date(Order.created_at) == today)
    if accessible_branch_ids:
        today_orders_query = today_orders_query.filter(Order.branchid.in_(accessible_branch_ids))
    today_orders_count = today_orders_query.count()
    
    # Get pending payments count (all payments are now completed, so this will be 0)
    pending_payments_count = 0
    
    # Get today's revenue (filtered by accessible branches)
    today_revenue_query = db.session.query(func.sum(Payment.amount)).join(Order).filter(
        func.date(Payment.created_at) == today,
        Payment.payment_status == 'completed'
    )
    if accessible_branch_ids:
        today_revenue_query = today_revenue_query.filter(Order.branchid.in_(accessible_branch_ids))
    today_revenue = today_revenue_query.scalar() or 0
    
    # Get recent pending orders (filtered by accessible branches)
    recent_orders_query = Order.query.filter_by(approvalstatus=False)
    if accessible_branch_ids:
        recent_orders_query = recent_orders_query.filter(Order.branchid.in_(accessible_branch_ids))
    recent_orders = recent_orders_query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Calculate total amount and payment status for each recent order
    for order in recent_orders:
        total_amount = 0
        if order.order_items:
            for item in order.order_items:
                price = float(item.final_price or item.original_price or 0)
                total_amount += float(item.quantity) * price
        order.total_amount = total_amount
        
        # Calculate payment status
        if total_amount == 0:
            order.payment_status = 'No Items'
        else:
            # Get all payments for this order to debug
            all_payments = Payment.query.filter_by(orderid=order.id).all()
            completed_payments = Payment.query.filter_by(orderid=order.id, payment_status='completed').all()
            
            # Calculate total payments using func.sum
            total_payments = db.session.query(func.sum(Payment.amount)).filter(
                Payment.orderid == order.id,
                Payment.payment_status == 'completed'
            ).scalar() or 0
            
            # Manual calculation as backup
            manual_total = 0
            for payment in completed_payments:
                if payment.amount:
                    manual_total += float(payment.amount)
            
            # Convert total_payments to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            
            # Use manual calculation if there's a discrepancy
            if abs(manual_total - total_payments_float) > 0.01:
                total_payments = manual_total
            else:
                total_payments = total_payments_float
            
            # Debug output
            print(f"Debug Dashboard - Order {order.id}: Total amount: {total_amount}, Total payments: {total_payments}")
            print(f"Debug Dashboard - Order {order.id}: All payments: {[p.id for p in all_payments]}")
            print(f"Debug Dashboard - Order {order.id}: Completed payments: {[p.id for p in completed_payments]}")
            
            # Convert to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            total_amount_float = float(total_amount) if total_amount else 0.0
            
            if total_payments_float >= total_amount_float:
                order.payment_status = 'Fully Paid'
            elif total_payments_float > 0:
                order.payment_status = 'Partially Paid'
            else:
                order.payment_status = 'Unpaid'
    
    # Get failed payments count (filtered by accessible branches)
    failed_payments_query = Payment.query.join(Order).filter_by(payment_status='failed')
    if accessible_branch_ids:
        failed_payments_query = failed_payments_query.filter(Order.branchid.in_(accessible_branch_ids))
    failed_payments_count = failed_payments_query.count()
    
    return render_template('dashboard.html',
                         pending_orders_count=pending_orders_count,
                         today_orders_count=today_orders_count,
                         pending_payments_count=pending_payments_count,
                         today_revenue=today_revenue,
                         recent_orders=recent_orders,
                         failed_payments_count=failed_payments_count)



@app.route('/profile')
@cashier_required
def profile():
    return render_template('profile.html')



# Order Management Routes
@app.route('/orders')
@cashier_required
def orders():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    if status_filter == 'pending':
        orders_query = Order.query.filter_by(approvalstatus=False)
    elif status_filter == 'approved':
        orders_query = Order.query.filter_by(approvalstatus=True)
    else:
        orders_query = Order.query
    
    # Filter by accessible branches
    if accessible_branch_ids:
        orders_query = orders_query.filter(Order.branchid.in_(accessible_branch_ids))
    
    orders = orders_query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate total amount and payment status for each order
    for order in orders.items:
        total_amount = 0
        if order.order_items:
            for item in order.order_items:
                price = float(item.final_price or item.original_price or 0)
                total_amount += float(item.quantity) * price
        order.total_amount = total_amount
        
        # Calculate payment status
        if total_amount == 0:
            order.payment_status = 'No Items'
        else:
            # Get all payments for this order to debug
            all_payments = Payment.query.filter_by(orderid=order.id).all()
            completed_payments = Payment.query.filter_by(orderid=order.id, payment_status='completed').all()
            
            # Calculate total payments using func.sum
            total_payments = db.session.query(func.sum(Payment.amount)).filter(
                Payment.orderid == order.id,
                Payment.payment_status == 'completed'
            ).scalar() or 0
            
            # Manual calculation as backup
            manual_total = 0
            for payment in completed_payments:
                if payment.amount:
                    manual_total += float(payment.amount)
            
            # Convert total_payments to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            
            # Use manual calculation if there's a discrepancy
            if abs(manual_total - total_payments_float) > 0.01:
                total_payments = manual_total
            else:
                total_payments = total_payments_float
            
            # Debug output
            print(f"Debug Orders - Order {order.id}: Total amount: {total_amount}, Total payments: {total_payments}")
            print(f"Debug Orders - Order {order.id}: All payments: {[p.id for p in all_payments]}")
            print(f"Debug Orders - Order {order.id}: Completed payments: {[p.id for p in completed_payments]}")
            
            # Convert to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            total_amount_float = float(total_amount) if total_amount else 0.0
            
            if total_payments_float >= total_amount_float:
                order.payment_status = 'Fully Paid'
            elif total_payments_float > 0:
                order.payment_status = 'Partially Paid'
            else:
                order.payment_status = 'Unpaid'
    
    return render_template('orders.html', orders=orders, status_filter=status_filter)

@app.route('/order/<int:order_id>')
@cashier_required
def view_order(order_id):
    from sqlalchemy import func
    
    order = Order.query.options(
        db.joinedload(Order.order_items).joinedload(OrderItem.branch_product).joinedload(BranchProduct.catalog_product)
    ).get_or_404(order_id)
    
    # Check if user has access to this order's branch
    if not current_user.has_branch_access(order.branchid):
        flash('Access denied. You do not have permission to view this order.', 'error')
        return redirect(url_for('orders'))
    
    # Calculate total amount from order items
    total_amount = 0
    if order.order_items:
        for item in order.order_items:
            price = float(item.final_price or item.original_price or 0)
            total_amount += float(item.quantity) * price
    
    # Calculate total payments for this order
    payments_sum_query = db.session.query(func.sum(Payment.amount)).filter(
        Payment.orderid == order.id,
        Payment.payment_status == 'completed'
    )
    total_payments = payments_sum_query.scalar() or 0
    
    # Debug: Check the raw query result
    print(f"Debug - Raw payments sum query result: {payments_sum_query.scalar()}")
    print(f"Debug - Total payments after scalar: {total_payments}")
    print(f"Debug - Type of total_payments: {type(total_payments)}")
    
    # Debug: Check if there are any payments at all for this order
    all_payments = Payment.query.filter_by(orderid=order.id).all()
    completed_payments = Payment.query.filter_by(orderid=order.id, payment_status='completed').all()
    
    print(f"Debug - Order {order.id}: Total amount: {total_amount}, Total payments: {total_payments}")
    print(f"Debug - All payments for order {order.id}: {[p.id for p in all_payments]}")
    print(f"Debug - Completed payments: {[p.id for p in completed_payments]}")
    
    for payment in all_payments:
        print(f"Debug - Payment {payment.id}: Amount: {payment.amount}, Status: {payment.payment_status}")
    
    # Determine if order is fully paid (convert to float for comparison)
    total_payments_float = float(total_payments) if total_payments else 0.0
    total_amount_float = float(total_amount) if total_amount else 0.0
    
    is_fully_paid = total_payments_float >= total_amount_float
    remaining_amount = max(0, total_amount_float - total_payments_float)
    
    # Ensure all variables are properly initialized
    if total_amount is None:
        total_amount = 0.0
    if total_payments is None:
        total_payments = 0.0
    if remaining_amount is None:
        remaining_amount = 0.0
    if is_fully_paid is None:
        is_fully_paid = False
    
    # Alternative calculation: manually sum completed payments
    manual_total = 0
    for payment in completed_payments:
        if payment.amount:
            manual_total += float(payment.amount)
    
    print(f"Debug - Manual total from completed payments: {manual_total}")
    print(f"Debug - Comparison: func.sum result = {total_payments}, manual sum = {manual_total}")
    
    # Convert total_payments to float for comparison
    total_payments_float = float(total_payments) if total_payments else 0.0
    
    # Use the manual calculation if there's a discrepancy
    if abs(manual_total - total_payments_float) > 0.01:
        print(f"Debug - WARNING: Discrepancy detected! Using manual calculation.")
        total_payments = manual_total
    else:
        total_payments = total_payments_float
    print(f"Debug - Total payments: {total_payments}")
    # Determine payment status for display
    if total_amount == 0:
        payment_status = 'No Items'
    elif is_fully_paid:
        payment_status = 'Fully Paid'
    elif total_payments > 0:
        payment_status = 'Partially Paid'
    else:
        payment_status = 'Unpaid'
    # Ensure payment_status is set
    if 'payment_status' not in locals() or payment_status is None:
        payment_status = 'Unpaid'
    
    print(f"Debug - Payment status: {payment_status}")  
    print(f"Debug - About to render template with order {order.id}")
    try:
        return render_template('view_order.html', 
                             order=order, 
                             total_amount=float(total_amount),
                             total_payments=float(total_payments),
                             is_fully_paid=is_fully_paid,
                             remaining_amount=remaining_amount,
                             payment_status=payment_status)
    except Exception as e:
        print(f"Debug - Error rendering template: {str(e)}")
        flash(f'Error displaying order: {str(e)}', 'error')
        return redirect(url_for('orders'))

@app.route('/order/<int:order_id>/approve', methods=['POST'])
@cashier_required
def approve_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if user has access to this order's branch
    if not current_user.has_branch_access(order.branchid):
        flash('Access denied. You do not have permission to approve this order.', 'error')
        return redirect(url_for('orders'))
    
    # Check if order is already approved
    if order.approvalstatus:
        flash(f'Order #{order.id} is already approved.', 'warning')
        return redirect(url_for('view_order', order_id=order_id))
    
    # Check if order has items
    if not order.order_items:
        flash('Cannot approve order with no items.', 'error')
        return redirect(url_for('view_order', order_id=order_id))
    
    # Check stock availability for informational purposes (but allow approval)
    low_stock_warnings = []
    missing_products = []
    
    for item in order.order_items:
        # Handle both regular products and manual items
        if item.branch_productid:
            branch_product = BranchProduct.query.get(item.branch_productid)
            if not branch_product:
                missing_products.append(f"Branch Product ID {item.branch_productid}")
                continue
            
            # Warn about low stock but don't block approval
            if branch_product.stock is not None and Decimal(str(branch_product.stock)) < Decimal(str(item.quantity)):
                product_name = branch_product.catalog_product.name if branch_product.catalog_product else "Unknown Product"
                low_stock_warnings.append({
                    'name': product_name,
                    'available': float(branch_product.stock),
                    'requested': float(item.quantity),
                    'shortage': float(Decimal(str(item.quantity)) - Decimal(str(branch_product.stock)))
                })
        else:
            # This is a manual item without a product relationship
            missing_products.append(f"Manual item: {item.product_name or 'Unnamed'}")
    
    # Show warning about missing products but don't block approval
    if missing_products:
        missing_msg = "⚠️ Some order items have missing product information (stock tracking disabled): " + ", ".join(missing_products)
        flash(missing_msg, 'warning')
    
    # Show warning about low stock items
    if low_stock_warnings:
        warning_msg = "⚠️ Low stock warning for: "
        for product in low_stock_warnings:
            warning_msg += f"{product['name']} (Available: {product['available']}, Requested: {product['requested']}, Shortage: {product['shortage']}); "
        flash(warning_msg, 'warning')
    
    try:
        # Approve the order
        order.approvalstatus = True
        order.approved_at = datetime.now()
        
        # Reduce stock quantities and create stock transactions (only for products with valid relationships)
        for item in order.order_items:
            if item.branch_productid:
                branch_product = BranchProduct.query.get(item.branch_productid)
                if branch_product:
                    previous_stock = Decimal(str(branch_product.stock or 0))
                    quantity_decimal = Decimal(str(item.quantity))
                    new_stock = previous_stock - quantity_decimal
                    
                    # Update branch product stock (can go negative for backorders)
                    branch_product.stock = new_stock
                    
                    # Create stock transaction record
                    stock_transaction = StockTransaction(
                        branch_productid=item.branch_productid,
                        userid=current_user.id,
                        transaction_type='remove',
                        quantity=item.quantity,
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        notes=f'Stock reduced due to order #{order.id} approval (Backorder: {float(quantity_decimal - previous_stock) if previous_stock < quantity_decimal else 0} units)'
                    )
                    db.session.add(stock_transaction)
                else:
                    # Branch product not found - skip stock transaction (no product to track)
                    pass
            else:
                # Manual item without branch product ID - skip stock transaction (no product to track)
                pass
        
        db.session.commit()
        
        # Customize success message based on stock situation
        if low_stock_warnings:
            flash(f'Order #{order.id} has been approved successfully! ⚠️ Some items are on backorder due to insufficient stock.', 'success')
        else:
            flash(f'Order #{order.id} has been approved successfully! Stock quantities have been updated where applicable.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve order: {str(e)}', 'error')
        print(f"Error approving order {order_id}: {str(e)}")
    
    return redirect(url_for('view_order', order_id=order_id))

@app.route('/order/<int:order_id>/cancel', methods=['POST'])
@cashier_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if user has access to this order's branch
    if not current_user.has_branch_access(order.branchid):
        flash('Access denied. You do not have permission to cancel this order.', 'error')
        return redirect(url_for('orders'))
    
    # Check if order is approved
    if not order.approvalstatus:
        flash(f'Order #{order.id} is not approved yet. Cannot cancel.', 'warning')
        return redirect(url_for('view_order', order_id=order_id))
    
    # Check if order has items
    if not order.order_items:
        flash('Cannot cancel order with no items.', 'error')
        return redirect(url_for('view_order', order_id=order_id))
    
    try:
        # Cancel the order
        order.approvalstatus = False
        order.approved_at = None
        
        # Restore stock quantities and create stock transactions (only for products with valid relationships)
        for item in order.order_items:
            if item.branch_productid:
                branch_product = BranchProduct.query.get(item.branch_productid)
                if branch_product:
                    previous_stock = Decimal(str(branch_product.stock or 0))
                    quantity_decimal = Decimal(str(item.quantity))
                    new_stock = previous_stock + quantity_decimal
                    
                    # Update branch product stock
                    branch_product.stock = new_stock
                    
                    # Create stock transaction record for restoration
                    stock_transaction = StockTransaction(
                        branch_productid=item.branch_productid,
                        userid=current_user.id,
                        transaction_type='add',
                        quantity=item.quantity,
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        notes=f'Stock restored due to order #{order.id} cancellation'
                    )
                    db.session.add(stock_transaction)
                else:
                    # Branch product not found - skip stock transaction (no product to track)
                    pass
            else:
                # Manual item without branch product ID - skip stock transaction (no product to track)
                pass
        
        db.session.commit()
        flash(f'Order #{order.id} has been cancelled successfully! Stock quantities have been restored where applicable.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to cancel order: {str(e)}', 'error')
        print(f"Error cancelling order {order_id}: {str(e)}")
    
    return redirect(url_for('view_order', order_id=order_id))

@app.route('/order/<int:order_id>/process-payment', methods=['GET', 'POST'])
@cashier_required
def process_payment_from_order(order_id):
    from sqlalchemy import func
    
    order = Order.query.get_or_404(order_id)
    
    # Check if user has access to this order's branch
    if not current_user.has_branch_access(order.branchid):
        flash('Access denied. You do not have permission to process payments for this order.', 'error')
        return redirect(url_for('orders'))
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method')
        reference_number = request.form.get('reference_number')
        notes = request.form.get('notes')
        
        if not amount or not payment_method:
            flash('Please fill in all required fields.', 'error')
            return render_template('process_payment.html', order=order)
        
        # Validate amount is a valid number
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                flash('Payment amount must be greater than 0.', 'error')
                return render_template('process_payment.html', order=order)
        except ValueError:
            flash('Please enter a valid payment amount.', 'error')
            return render_template('process_payment.html', order=order)
        
        try:
            # Calculate total amount for the order
            total_amount = 0
            if order.order_items:
                for item in order.order_items:
                    price = float(item.final_price or item.original_price or 0)
                    total_amount += float(item.quantity) * price
            
            # Calculate total payments for this order (excluding the new payment being created)
            existing_payments = db.session.query(func.sum(Payment.amount)).filter(
                Payment.orderid == order.id,
                Payment.payment_status == 'completed'
            ).scalar() or 0
            
            # Calculate remaining amount (ensure both are float)
            remaining_amount = float(total_amount) - float(existing_payments)
            
            # Payment status is always completed for cashier payments
            payment_status = 'completed'
            
            # Create new payment
            new_payment = Payment(
                orderid=order.id,
                userid=order.userid,
                amount=amount,
                payment_method=payment_method,
                payment_status=payment_status,
                reference_number=reference_number,
                notes=notes
            )
            
            # Set payment date since all payments are completed
            new_payment.payment_date = datetime.now()
            
            print(f"Debug - Payment object created: {new_payment}")
            print(f"Debug - Payment validation: orderid={new_payment.orderid}, userid={new_payment.userid}, amount={new_payment.amount}")
            
            db.session.add(new_payment)
            print(f"Debug - Payment added to session")
            
            # Check for any validation errors
            try:
                db.session.flush()
                print(f"Debug - Payment flushed to database successfully")
            except Exception as flush_error:
                print(f"Debug - Flush error: {str(flush_error)}")
                raise flush_error
            
            db.session.commit()
            print(f"Debug - Payment committed to database successfully")
            
            print(f"Debug - Payment created successfully: ID {new_payment.id}, Amount: {new_payment.amount}, Status: {new_payment.payment_status}")
            
            # Check if this payment completes the order
            if float(amount) >= remaining_amount:
                flash(f'Payment of KSH {amount} has been completed successfully! Order is now fully paid.', 'success')
            else:
                flash(f'Payment of KSH {amount} has been completed successfully! (Partial payment - KSH {remaining_amount - float(amount):.2f} remaining)', 'success')
            
            print(f"Debug - Flash messages set successfully")
            print(f"Debug - Redirecting to view_order for order {order_id}")
            
            try:
                return redirect(url_for('view_order', order_id=order_id))
            except Exception as redirect_error:
                print(f"Debug - Redirect error: {str(redirect_error)}")
                flash(f'Payment created but redirect failed: {str(redirect_error)}', 'warning')
                return redirect(url_for('orders'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Debug - Error creating payment: {str(e)}")
            print(f"Debug - Error type: {type(e)}")
            print(f"Debug - Error details: {e}")
            flash(f'Failed to create payment: {str(e)}', 'error')
    
    # Calculate total amount for the order
    total_amount = 0
    if order.order_items:
        for item in order.order_items:
            price = float(item.final_price or item.original_price or 0)
            total_amount += float(item.quantity) * price
    
    # Calculate total payments for this order
    total_payments = db.session.query(func.sum(Payment.amount)).filter(
        Payment.orderid == order.id,
        Payment.payment_status == 'completed'
    ).scalar() or 0
    
    # Calculate remaining amount
    remaining_amount = max(0, float(total_amount) - float(total_payments))
    
    return render_template('process_payment.html', 
                         order=order, 
                         total_amount=float(total_amount),
                         total_payments=float(total_payments),
                         remaining=remaining_amount)

# Payment Management Routes
@app.route('/payments')
@cashier_required
def payments():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    if status_filter == 'completed':
        payments_query = Payment.query.join(Order).filter_by(payment_status='completed')
    elif status_filter == 'failed':
        payments_query = Payment.query.join(Order).filter_by(payment_status='failed')
    else:
        payments_query = Payment.query.join(Order)
    
    # Filter by accessible branches
    if accessible_branch_ids:
        payments_query = payments_query.filter(Order.branchid.in_(accessible_branch_ids))
    
    payments = payments_query.order_by(Payment.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('payments.html', payments=payments, status_filter=status_filter)

@app.route('/payment/<int:payment_id>')
@cashier_required
def view_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    
    # Check if user has access to this payment's order branch
    if not current_user.has_branch_access(payment.order.branchid):
        flash('Access denied. You do not have permission to view this payment.', 'error')
        return redirect(url_for('payments'))
    
    # Calculate total amount for the related order if it exists
    if hasattr(payment, 'order') and payment.order:
        total_amount = 0
        if payment.order.order_items:
            for item in payment.order.order_items:
                price = float(item.final_price or item.original_price or 0)
                total_amount += float(item.quantity) * price
        payment.order.total_amount = total_amount
    
    return render_template('view_payment.html', payment=payment)

@app.route('/payment/<int:payment_id>/process', methods=['POST'])
@cashier_required
def process_payment(payment_id):
    from sqlalchemy import func
    
    payment = Payment.query.get_or_404(payment_id)
    
    # Check if user has access to this payment's order branch
    if not current_user.has_branch_access(payment.order.branchid):
        flash('Access denied. You do not have permission to process this payment.', 'error')
        return redirect(url_for('payments'))
    
    action = request.form.get('action')
    
    if action == 'complete':
        payment.payment_status = 'completed'
        payment.payment_date = datetime.now()
        
        # Check if this completes the order
        if hasattr(payment, 'order') and payment.order:
            total_amount = 0
            if payment.order.order_items:
                for item in payment.order.order_items:
                    price = float(item.final_price or item.original_price or 0)
                    total_amount += float(item.quantity) * price
            
            # Calculate total payments for this order
            total_payments = db.session.query(func.sum(Payment.amount)).filter(
                Payment.orderid == payment.order.id,
                Payment.payment_status == 'completed'
            ).scalar() or 0
            
            # Convert to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            total_amount_float = float(total_amount) if total_amount else 0.0
            
            if total_payments_float >= total_amount_float:
                flash(f'Payment #{payment.id} marked as completed! Order #{payment.order.id} is now fully paid.', 'success')
            else:
                flash(f'Payment #{payment.id} marked as completed!', 'success')
        else:
            flash(f'Payment #{payment.id} marked as completed!', 'success')
            
    elif action == 'fail':
        payment.payment_status = 'failed'
        flash(f'Payment #{payment.id} marked as failed!', 'warning')
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Failed to update payment status. Please try again.', 'error')
    
    return redirect(url_for('view_payment', payment_id=payment_id))

# Sales Report Route
@app.route('/sales-report')
@cashier_required
def sales_report():
    from datetime import datetime, timedelta
    
    # Get date range from query parameters
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    # Convert to datetime objects
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get sales data (filtered by accessible branches)
    sales_data_query = db.session.query(
        func.date(Payment.created_at).label('date'),
        func.count(Payment.id).label('payment_count'),
        func.sum(Payment.amount).label('total_amount')
    ).join(Order).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt
    )
    
    # Filter by accessible branches
    if accessible_branch_ids:
        sales_data_query = sales_data_query.filter(Order.branchid.in_(accessible_branch_ids))
    
    sales_data = sales_data_query.group_by(func.date(Payment.created_at)).order_by(func.date(Payment.created_at)).all()
    
    # Calculate totals
    total_revenue = sum(row.total_amount for row in sales_data if row.total_amount)
    total_payments = sum(row.payment_count for row in sales_data)
    
    return render_template('sales_report.html', 
                         sales_data=sales_data,
                         start_date=start_date,
                         end_date=end_date,
                         total_revenue=total_revenue,
                         total_payments=total_payments)

@app.route('/sales-report/daily-details/<date>')
@cashier_required
def daily_sales_details(date):
    """Show detailed breakdown of sales for a specific date"""
    try:
        # Parse the date
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # Get accessible branch IDs for current user
        accessible_branch_ids = get_user_accessible_branch_ids()
        
        # Get all payments for the specific date (filtered by accessible branches)
        payments_query = db.session.query(Payment).join(Order).filter(
            Payment.payment_status == 'completed',
            func.date(Payment.created_at) == date_obj.date()
        )
        
        # Filter by accessible branches
        if accessible_branch_ids:
            payments_query = payments_query.filter(Order.branchid.in_(accessible_branch_ids))
        
        payments = payments_query.order_by(Payment.created_at.desc()).all()
        
        # Get order details for each payment
        payment_details = []
        total_revenue = 0
        
        for payment in payments:
            order = Order.query.get(payment.orderid)
            if order:
                # Get order items
                order_items = []
                for item in order.order_items:
                    if item.branch_product and item.branch_product.catalog_product:
                        product_name = item.branch_product.catalog_product.name
                    else:
                        product_name = item.product_name or 'Manual Item'
                    order_items.append({
                        'product_name': product_name,
                        'quantity': float(item.quantity),
                        'unit_price': float(item.final_price or item.original_price or 0),
                        'total_price': float(item.final_price or item.original_price or 0) * float(item.quantity)
                    })
                
                # Determine customer/sales person name based on order type
                if order.ordertype and order.ordertype.name.lower() == 'walk-in':
                    # For walk-in orders, show sales person name (user who created the order)
                    display_name = f"{order.user.firstname} {order.user.lastname} (Sales Person)"
                    name_type = "sales_person"
                else:
                    # For regular orders, show customer name
                    display_name = f"{order.user.firstname} {order.user.lastname}"
                    name_type = "customer"
                
                payment_details.append({
                    'payment': payment,
                    'order': order,
                    'order_items': order_items,
                    'customer_name': display_name,
                    'name_type': name_type,
                    'payment_method': payment.payment_method,
                    'payment_time': payment.created_at
                })
                
                total_revenue += float(payment.amount)
        
        return render_template('daily_sales_details.html',
                             date=date_obj,
                             payment_details=payment_details,
                             total_revenue=total_revenue,
                             total_payments=len(payments))
                             
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('sales_report'))

# PDF Export Route for Sales Report
@app.route('/sales-report/export-pdf')
@cashier_required
def export_sales_report_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from io import BytesIO
    from datetime import datetime, timedelta
    import os
    
    # Get date range from query parameters
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    # Convert to datetime objects
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get branch information for the accessible branches
    accessible_branches = current_user.get_accessible_branches()
    branch_names = [branch.name for branch in accessible_branches]
    
    # Determine branch display name
    if len(branch_names) == 1:
        branch_display_name = branch_names[0]
    elif len(branch_names) > 1:
        branch_display_name = "All Branches"
    else:
        branch_display_name = "All Branches"
    
    # Get all payments for the date range (filtered by accessible branches)
    payments_query = db.session.query(Payment).join(Order).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt
    )
    
    # Filter by accessible branches
    if accessible_branch_ids:
        payments_query = payments_query.filter(Order.branchid.in_(accessible_branch_ids))
    
    payments = payments_query.order_by(Payment.created_at.desc()).all()
    
    # Get order details for each payment
    payment_details = []
    total_revenue = 0
    
    for payment in payments:
        order = Order.query.get(payment.orderid)
        if order:
            # Get order items
            order_items = []
            for item in order.order_items:
                if item.branch_product and item.branch_product.catalog_product:
                    product_name = item.branch_product.catalog_product.name
                else:
                    product_name = item.product_name or 'Manual Item'
                order_items.append({
                    'product_name': product_name,
                    'quantity': float(item.quantity),
                    'unit_price': float(item.final_price or item.original_price or 0),
                    'total_price': float(item.final_price or item.original_price or 0) * float(item.quantity)
                })
            
            # Determine customer/sales person name based on order type
            if order.ordertype and order.ordertype.name.lower() == 'walk-in':
                # For walk-in orders, show sales person name (user who created the order)
                display_name = f"{order.user.firstname} {order.user.lastname} (Sales Person)"
                name_type = "sales_person"
            else:
                # For regular orders, show customer name
                display_name = f"{order.user.firstname} {order.user.lastname}"
                name_type = "customer"
            
            payment_details.append({
                'payment': payment,
                'order': order,
                'order_items': order_items,
                'customer_name': display_name,
                'name_type': name_type,
                'payment_method': payment.payment_method,
                'payment_time': payment.created_at,
                'branch_name': order.branch.name if order.branch else 'Unknown Branch'
            })
            
            total_revenue += float(payment.amount)
    
    # Create PDF with better margins to match reference
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    
    # Define styles to match reference PDF
    styles = getSampleStyleSheet()
    
    # Report Title Style
    report_title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=22,
        spaceAfter=25,
        alignment=1,  # Center alignment
        textColor=colors.black,
        fontName='Helvetica-Bold'
    )
    
    # Report Details Style
    report_details_style = ParagraphStyle(
        'ReportDetails',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=5,
        alignment=0,  # Left alignment
        textColor=colors.black,
        fontName='Helvetica'
    )
    
    # Section Heading Style
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=15,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    # Normal text style
    normal_style = styles['Normal']
    
    # Recreate the ABZ Hardware letterhead manually
    
    # Try to load the logo for the left side
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
        if os.path.exists(logo_path):
            logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
            logo_cell = logo_image
        else:
            # Fallback to text if logo not found
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
            <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
            <b><font size=14 color="#1a365d">LIMITED</font></b>
            </para>
            ''', normal_style)
    except Exception as e:
        print(f"Error loading logo: {e}")
        # Fallback to text if logo fails to load
        logo_cell = Paragraph('''
        <para align=left>
        <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
        <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
        <b><font size=14 color="#1a365d">LIMITED</font></b>
        </para>
        ''', normal_style)
    
    # Create the letterhead table for proper layout
    letterhead_data = [[
        # Left side - Logo Image
        logo_cell,
        
        # Right side - Contact Information
        Paragraph('''
        <para align=right>
        <b><font size=11 color="#1a365d">Kombo Munyiri Road,</font></b><br/>
        <b><font size=11 color="#1a365d">Gikomba, Nairobi, Kenya</font></b><br/>
        <font size=9 color="#666666">0711 732 341 or 0725 000 055</font><br/>
        <font size=9 color="#666666">info@abzhardware.co.ke</font><br/>
        <font size=9 color="#666666">www.abzhardware.co.ke</font>
        </para>
        ''', normal_style)
    ]]
    
    # Create letterhead table
    letterhead_table = Table(letterhead_data, colWidths=[3.5*inch, 3.5*inch])
    letterhead_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    
    elements.append(letterhead_table)
    elements.append(Spacer(1, 10))
    
    # Add the colored line separator (yellow and dark blue)
    separator_data = [[""]]
    separator_table = Table(separator_data, colWidths=[7*inch], rowHeights=[0.05*inch])
    separator_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4b942')),  # Yellow color
    ]))
    
    elements.append(separator_table)
    elements.append(Spacer(1, 30))
    
    # Report Title
    elements.append(Paragraph("SALES REPORT", report_title_style))
    
    # Report details - Better formatting
    elements.append(Paragraph(f"Period: {start_dt.strftime('%B %d, %Y')} - {datetime.strptime(end_date, '%Y-%m-%d').strftime('%B %d, %Y')}", report_details_style))
    elements.append(Paragraph(f"Branch: {branch_display_name.upper()}", report_details_style))
    # Get branch location if available
    branch_location = accessible_branches[0].location if len(accessible_branches) == 1 else "Multiple Locations"
    elements.append(Paragraph(f"Location: {branch_location.upper()}", report_details_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", report_details_style))
    elements.append(Spacer(1, 25))
    
    # Calculate additional metrics
    total_items_sold = len(set(item['product_name'] for detail in payment_details for item in detail['order_items']))
    
    # Calculate actual profit from final_price vs buying_price directly from OrderItems
    total_profit = 0
    items_with_profit_data = 0
    items_without_profit_data = 0
    
    for detail in payment_details:
        order = detail['order']
        for order_item in order.order_items:
            # Get final_price and buying_price directly from OrderItem
            final_price = float(order_item.final_price or 0)
            buying_price = float(order_item.buying_price or 0)
            quantity = float(order_item.quantity or 0)
            
            # Calculate profit: (final_price - buying_price) * quantity
            if buying_price > 0 and final_price > 0:
                profit_per_unit = final_price - buying_price
                profit_for_item = profit_per_unit * quantity
                total_profit += profit_for_item
                items_with_profit_data += 1
            else:
                items_without_profit_data += 1
    
    # If we couldn't calculate profit from actual prices, fall back to estimation
    if total_profit == 0 and total_revenue > 0:
        # Estimate 20% profit margin if no buying prices available
        total_profit = total_revenue * 0.2
        print(f"Profit estimation used: {total_profit} (20% of revenue)")
    else:
        print(f"Actual profit calculated: {total_profit}")
        print(f"Items with profit data: {items_with_profit_data}, Items without: {items_without_profit_data}")
    
    # Summary section
    elements.append(Paragraph("SUMMARY", heading_style))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Revenue', f"KSh {total_revenue:,.0f}"],
        ['Total Payments', f"{len(payments):,}"],
        ['Total Items Sold', f"{total_items_sold:,}"],
        ['Total Profit', f"KSh {total_profit:,.0f}"]
    ]
    
    summary_table = Table(summary_data, colWidths=[2.8*inch, 2.8*inch])
    summary_table.setStyle(TableStyle([
        # Header row - Enhanced styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 15),
        ('TOPPADDING', (0, 0), (-1, 0), 15),
        
        # Data rows - Enhanced styling
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 12),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Metric names left aligned
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Values center aligned
        
        # Grid - Enhanced styling
        ('GRID', (0, 0), (-1, -1), 1.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Payment Details Table
    if payment_details:
        elements.append(Paragraph("PAYMENT DETAILS", heading_style))
        
        # Create payment details table
        payment_table_data = [['Payment ID', 'Order ID', 'Amount', 'Method', 'Status', 'Time']]
        for detail in payment_details:
            payment_table_data.append([
                str(detail['payment'].id),
                str(detail['order'].id),
                f"KSh {detail['payment'].amount:,.0f}",
                detail['payment_method'],
                'completed',
                detail['payment_time'].strftime('%H:%M')
            ])
        
        payment_table = Table(payment_table_data, colWidths=[1*inch, 1*inch, 1.5*inch, 1.5*inch, 1*inch, 1*inch])
        payment_table.setStyle(TableStyle([
            # Header row - Enhanced styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            
            # Data rows - Enhanced styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            
            # Grid - Enhanced styling
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        
        elements.append(payment_table)
        elements.append(Spacer(1, 20))
        
        # Sold Items Table
        elements.append(Paragraph("SOLD ITEMS", heading_style))
        
        # Collect all items from all orders
        all_items = []
        for detail in payment_details:
            order = detail['order']
            for order_item in order.order_items:
                # Get product name
                if order_item.branch_product and order_item.branch_product.catalog_product:
                    product_name = order_item.branch_product.catalog_product.name
                else:
                    product_name = order_item.product_name or 'Manual Item'
                
                # Get prices directly from OrderItem
                final_price = float(order_item.final_price or 0)
                buying_price = float(order_item.buying_price or 0)
                quantity = float(order_item.quantity or 0)
                total_price = final_price * quantity
                
                # Calculate profit: (final_price - buying_price) * quantity
                if buying_price > 0 and final_price > 0:
                    profit_per_unit = final_price - buying_price
                    profit = profit_per_unit * quantity
                else:
                    # Fall back to 20% estimation if no buying price available
                    profit = total_price * 0.2
                
                all_items.append({
                    'product_name': product_name,
                    'quantity': quantity,
                    'unit_price': final_price,
                    'total_price': total_price,
                    'profit': profit
                })
        
        # Create sold items table
        sold_items_data = [['Product', 'Quantity', 'Unit Price', 'Total', 'Profit']]
        for item in all_items:
            sold_items_data.append([
                item['product_name'],
                str(item['quantity']),
                f"KSh {item['unit_price']:,.0f}",
                f"KSh {item['total_price']:,.0f}",
                f"KSh {item['profit']:,.0f}"
            ])
        
        sold_items_table = Table(sold_items_data, colWidths=[2.8*inch, 1*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        sold_items_table.setStyle(TableStyle([
            # Header row - Enhanced styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            
            # Data rows - Enhanced styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Product names left aligned
            ('ALIGN', (1, 1), (4, -1), 'CENTER'),  # Other columns center aligned
            
            # Grid - Enhanced styling
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        
        elements.append(sold_items_table)
    else:
        elements.append(Paragraph("No payments found for this date range.", normal_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    # Generate filename with the requested format
    branch_slug = branch_display_name.lower().replace(' ', '_').replace('&', 'and')
    filename = f"sales_report_{branch_slug}_{start_date}_to_{end_date}.pdf"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

# PDF Export Route for Daily Sales Details
@app.route('/sales-report/daily-details/<date>/export-pdf')
@cashier_required
def export_daily_sales_pdf(date):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from io import BytesIO
    from datetime import datetime
    import os
    
    try:
        # Parse the date
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # Get accessible branch IDs for current user
        accessible_branch_ids = get_user_accessible_branch_ids()
        
        # Get branch information for the accessible branches
        accessible_branches = current_user.get_accessible_branches()
        branch_names = [branch.name for branch in accessible_branches]
        
        # Determine branch display name
        if len(branch_names) == 1:
            branch_display_name = branch_names[0]
        elif len(branch_names) > 1:
            branch_display_name = "All Branches"
        else:
            branch_display_name = "All Branches"
        
        # Get all payments for the specific date (filtered by accessible branches)
        payments_query = db.session.query(Payment).join(Order).filter(
            Payment.payment_status == 'completed',
            func.date(Payment.created_at) == date_obj.date()
        )
        
        # Filter by accessible branches
        if accessible_branch_ids:
            payments_query = payments_query.filter(Order.branchid.in_(accessible_branch_ids))
        
        payments = payments_query.order_by(Payment.created_at.desc()).all()
        
        # Get order details for each payment
        payment_details = []
        total_revenue = 0
        
        for payment in payments:
            order = Order.query.get(payment.orderid)
            if order:
                # Get order items
                order_items = []
                for item in order.order_items:
                    if item.branch_product and item.branch_product.catalog_product:
                        product_name = item.branch_product.catalog_product.name
                    else:
                        product_name = item.product_name or 'Manual Item'
                    order_items.append({
                        'product_name': product_name,
                        'quantity': float(item.quantity),
                        'unit_price': float(item.final_price or item.original_price or 0),
                        'total_price': float(item.final_price or item.original_price or 0) * float(item.quantity)
                    })
                
                # Determine customer/sales person name based on order type
                if order.ordertype and order.ordertype.name.lower() == 'walk-in':
                    # For walk-in orders, show sales person name (user who created the order)
                    display_name = f"{order.user.firstname} {order.user.lastname} (Sales Person)"
                    name_type = "sales_person"
                else:
                    # For regular orders, show customer name
                    display_name = f"{order.user.firstname} {order.user.lastname}"
                    name_type = "customer"
                
                payment_details.append({
                    'payment': payment,
                    'order': order,
                    'order_items': order_items,
                    'customer_name': display_name,
                    'name_type': name_type,
                    'payment_method': payment.payment_method,
                    'payment_time': payment.created_at,
                    'branch_name': order.branch.name if order.branch else 'Unknown Branch'
                })
                
                total_revenue += float(payment.amount)
        
        # Create PDF with better margins to match reference
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
        elements = []
        
        # Define styles to match reference PDF
        styles = getSampleStyleSheet()
        
        # Report Title Style
        report_title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=22,
            spaceAfter=25,
            alignment=1,  # Center alignment
            textColor=colors.black,
            fontName='Helvetica-Bold'
        )
        
        # Report Details Style
        report_details_style = ParagraphStyle(
            'ReportDetails',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=5,
            alignment=0,  # Left alignment
            textColor=colors.black,
            fontName='Helvetica'
        )
        
        # Section Heading Style
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=15,
            textColor=colors.darkblue,
            fontName='Helvetica-Bold'
        )
        
        # Normal text style
        normal_style = styles['Normal']
        
        # Recreate the ABZ Hardware letterhead manually
        
        # Try to load the logo for the left side
        try:
            logo_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
            if os.path.exists(logo_path):
                logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
                logo_cell = logo_image
            else:
                # Fallback to text if logo not found
                logo_cell = Paragraph('''
                <para align=left>
                <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
                <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
                <b><font size=14 color="#1a365d">LIMITED</font></b>
                </para>
                ''', normal_style)
        except Exception as e:
            print(f"Error loading logo: {e}")
            # Fallback to text if logo fails to load
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
            <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
            <b><font size=14 color="#1a365d">LIMITED</font></b>
            </para>
            ''', normal_style)
        
        # Create the letterhead table for proper layout
        letterhead_data = [[
            # Left side - Logo Image
            logo_cell,
            
            # Right side - Contact Information
            Paragraph('''
            <para align=right>
            <b><font size=11 color="#1a365d">Kombo Munyiri Road,</font></b><br/>
            <b><font size=11 color="#1a365d">Gikomba, Nairobi, Kenya</font></b><br/>
            <font size=9 color="#666666">0711 732 341 or 0725 000 055</font><br/>
            <font size=9 color="#666666">info@abzhardware.co.ke</font><br/>
            <font size=9 color="#666666">www.abzhardware.co.ke</font>
            </para>
            ''', normal_style)
        ]]
        
        # Create letterhead table
        letterhead_table = Table(letterhead_data, colWidths=[3.5*inch, 3.5*inch])
        letterhead_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ]))
        
        elements.append(letterhead_table)
        elements.append(Spacer(1, 10))
        
        # Add the colored line separator (yellow and dark blue)
        separator_data = [[""]]
        separator_table = Table(separator_data, colWidths=[7*inch], rowHeights=[0.05*inch])
        separator_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4b942')),  # Yellow color
        ]))
        
        elements.append(separator_table)
        elements.append(Spacer(1, 30))
        
        # Report Title
        elements.append(Paragraph("DAILY SALES REPORT", report_title_style))
        
        # Report details - Better formatting
        elements.append(Paragraph(f"Date: {date_obj.strftime('%A, %B %d, %Y')}", report_details_style))
        elements.append(Paragraph(f"Branch: {branch_display_name.upper()}", report_details_style))
        # Get branch location if available
        branch_location = accessible_branches[0].location if len(accessible_branches) == 1 else "Multiple Locations"
        elements.append(Paragraph(f"Location: {branch_location.upper()}", report_details_style))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", report_details_style))
        elements.append(Spacer(1, 25))
        
        # Calculate additional metrics
        total_items_sold = len(set(item['product_name'] for detail in payment_details for item in detail['order_items']))
        
        # Calculate actual profit from final_price vs buying_price directly from OrderItems
        total_profit = 0
        items_with_profit_data = 0
        items_without_profit_data = 0
        
        for detail in payment_details:
            order = detail['order']
            for order_item in order.order_items:
                # Get final_price and buying_price directly from OrderItem
                final_price = float(order_item.final_price or 0)
                buying_price = float(order_item.buying_price or 0)
                quantity = float(order_item.quantity or 0)
                
                # Calculate profit: (final_price - buying_price) * quantity
                if buying_price > 0 and final_price > 0:
                    profit_per_unit = final_price - buying_price
                    profit_for_item = profit_per_unit * quantity
                    total_profit += profit_for_item
                    items_with_profit_data += 1
                else:
                    items_without_profit_data += 1
        
        # If we couldn't calculate profit from actual prices, fall back to estimation
        if total_profit == 0 and total_revenue > 0:
            # Estimate 20% profit margin if no buying prices available
            total_profit = total_revenue * 0.2
            print(f"Profit estimation used: {total_profit} (20% of revenue)")
        else:
            print(f"Actual profit calculated: {total_profit}")
            print(f"Items with profit data: {items_with_profit_data}, Items without: {items_without_profit_data}")
        
        # Summary section
        elements.append(Paragraph("SUMMARY", heading_style))
        
        summary_data = [
            ['Metric', 'Value'],
            ['Total Revenue', f"KSh {total_revenue:,.0f}"],
            ['Total Payments', f"{len(payments):,}"],
            ['Total Items Sold', f"{total_items_sold:,}"],
            ['Total Profit', f"KSh {total_profit:,.0f}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[2.8*inch, 2.8*inch])
        summary_table.setStyle(TableStyle([
            # Header row - Enhanced styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 15),
            ('TOPPADDING', (0, 0), (-1, 0), 15),
            
            # Data rows - Enhanced styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 12),
            ('TOPPADDING', (0, 1), (-1, -1), 12),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Metric names left aligned
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Values center aligned
            
            # Grid - Enhanced styling
            ('GRID', (0, 0), (-1, -1), 1.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Payment Details Table
        if payment_details:
            elements.append(Paragraph("PAYMENT DETAILS", heading_style))
            
            # Create payment details table
            payment_table_data = [['Payment ID', 'Order ID', 'Amount', 'Method', 'Status', 'Time']]
            for detail in payment_details:
                payment_table_data.append([
                    str(detail['payment'].id),
                    str(detail['order'].id),
                    f"KSh {detail['payment'].amount:,.0f}",
                    detail['payment_method'],
                    'completed',
                    detail['payment_time'].strftime('%H:%M')
                ])
            
            payment_table = Table(payment_table_data, colWidths=[1*inch, 1*inch, 1.5*inch, 1.5*inch, 1*inch, 1*inch])
            payment_table.setStyle(TableStyle([
                # Header row - Enhanced styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                
                # Data rows - Enhanced styling
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                
                # Grid - Enhanced styling
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            
            elements.append(payment_table)
            elements.append(Spacer(1, 20))
            
            # Sold Items Table
            elements.append(Paragraph("SOLD ITEMS", heading_style))
            
            # Collect all items from all orders
            all_items = []
            for detail in payment_details:
                order = detail['order']
                for order_item in order.order_items:
                    # Get product name
                    if order_item.branch_product and order_item.branch_product.catalog_product:
                        product_name = order_item.branch_product.catalog_product.name
                    else:
                        product_name = order_item.product_name or 'Manual Item'
                    
                    # Get prices directly from OrderItem
                    final_price = float(order_item.final_price or 0)
                    buying_price = float(order_item.buying_price or 0)
                    quantity = float(order_item.quantity or 0)
                    total_price = final_price * quantity
                    
                    # Calculate profit: (final_price - buying_price) * quantity
                    if buying_price > 0 and final_price > 0:
                        profit_per_unit = final_price - buying_price
                        profit = profit_per_unit * quantity
                    else:
                        # Fall back to 20% estimation if no buying price available
                        profit = total_price * 0.2
                    
                    all_items.append({
                        'product_name': product_name,
                        'quantity': quantity,
                        'unit_price': final_price,
                        'total_price': total_price,
                        'profit': profit
                    })
            
            # Create sold items table
            sold_items_data = [['Product', 'Quantity', 'Unit Price', 'Total', 'Profit']]
            for item in all_items:
                sold_items_data.append([
                    item['product_name'],
                    str(item['quantity']),
                    f"KSh {item['unit_price']:,.0f}",
                    f"KSh {item['total_price']:,.0f}",
                    f"KSh {item['profit']:,.0f}"
                ])
            
            sold_items_table = Table(sold_items_data, colWidths=[2.8*inch, 1*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            sold_items_table.setStyle(TableStyle([
                # Header row - Enhanced styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                
                # Data rows - Enhanced styling
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Product names left aligned
                ('ALIGN', (1, 1), (4, -1), 'CENTER'),  # Other columns center aligned
                
                # Grid - Enhanced styling
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            
            elements.append(sold_items_table)
        else:
            elements.append(Paragraph("No payments found for this date.", normal_style))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        # Generate filename with the requested format
        branch_slug = branch_display_name.lower().replace(' ', '_').replace('&', 'and')
        filename = f"daily_sales_report_{branch_slug}_{date}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('sales_report'))

# Stock Transactions Route
@app.route('/stock-transactions')
@cashier_required
def stock_transactions():
    page = request.args.get('page', 1, type=int)
    transaction_type = request.args.get('type', 'all')
    product_id = request.args.get('product_id', type=int)
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Build query with branch filtering
    query = StockTransaction.query.join(BranchProduct)
    
    # Filter by accessible branches
    if accessible_branch_ids:
        query = query.filter(BranchProduct.branchid.in_(accessible_branch_ids))
    
    if transaction_type != 'all':
        query = query.filter_by(transaction_type=transaction_type)
    
    if product_id:
        query = query.filter_by(branch_productid=product_id)
    
    # Get stock transactions with pagination
    transactions = query.order_by(StockTransaction.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get all branch products for filter dropdown (filtered by accessible branches)
    products_query = BranchProduct.query
    if accessible_branch_ids:
        products_query = products_query.filter(BranchProduct.branchid.in_(accessible_branch_ids))
    products = products_query.all()
    
    return render_template('stock_transactions.html', 
                         transactions=transactions, 
                         transaction_type=transaction_type,
                         product_id=product_id,
                         products=products)

# Current Stock Levels Route
@app.route('/stock-levels')
@cashier_required
def stock_levels():
    page = request.args.get('page', 1, type=int)
    branch_id = request.args.get('branch_id', type=int)
    low_stock = request.args.get('low_stock', type=bool)
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Build query with branch filtering
    query = BranchProduct.query
    
    # Filter by accessible branches
    if accessible_branch_ids:
        query = query.filter(BranchProduct.branchid.in_(accessible_branch_ids))
    
    if branch_id:
        # Also check if user has access to the requested branch
        if branch_id not in accessible_branch_ids:
            flash('Access denied. You do not have permission to view this branch.', 'error')
            return redirect(url_for('stock_levels'))
        query = query.filter_by(branchid=branch_id)
    
    if low_stock:
        query = query.filter(BranchProduct.stock < Decimal('10.000'))  # Show products with less than 10 in stock
    
    # Add backorder filter option
    backorder = request.args.get('backorder', type=bool)
    if backorder:
        query = query.filter(BranchProduct.stock < Decimal('0.000'))  # Show products with negative stock (backorders)
    
    # Get products with pagination
    products = query.order_by(BranchProduct.catalog_product.has(ProductCatalog.name)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get accessible branches for filter dropdown
    branches = get_user_accessible_branches()
    
    return render_template('stock_levels.html', 
                         products=products, 
                         branch_id=branch_id,
                         low_stock=low_stock,
                         backorder=backorder,
                         branches=branches)

# Manual Stock Adjustment Route
@app.route('/stock-adjustment', methods=['GET', 'POST'])
@cashier_required
def stock_adjustment():
    if request.method == 'POST':
        product_id = request.form.get('product_id', type=int)
        adjustment_type = request.form.get('adjustment_type')  # 'add' or 'remove'
        quantity = request.form.get('quantity', type=float)
        notes = request.form.get('notes', '')
        
        if not product_id or not adjustment_type or not quantity or quantity <= 0:
            flash('Please fill in all required fields with valid values.', 'error')
            return redirect(url_for('stock_adjustment'))
        
        branch_product = BranchProduct.query.get_or_404(product_id)
        
        # Check if user has access to this product's branch
        if not current_user.has_branch_access(branch_product.branchid):
            flash('Access denied. You do not have permission to adjust stock for this product.', 'error')
            return redirect(url_for('stock_adjustment'))
        
        try:
            previous_stock = Decimal(str(branch_product.stock or 0))
            quantity_decimal = Decimal(str(quantity))
            
            if adjustment_type == 'add':
                new_stock = previous_stock + quantity_decimal
            else:  # remove
                # Allow negative stock for backorders
                new_stock = previous_stock - quantity_decimal
            
            # Update branch product stock
            branch_product.stock = new_stock
            
            # Create stock transaction record
            stock_transaction = StockTransaction(
                branch_productid=product_id,
                userid=current_user.id,
                transaction_type=adjustment_type,
                quantity=quantity,
                previous_stock=previous_stock,
                new_stock=new_stock,
                notes=f'Manual stock adjustment: {notes}'
            )
            db.session.add(stock_transaction)
            
            db.session.commit()
            
            action = 'added to' if adjustment_type == 'add' else 'removed from'
            stock_status = f"New stock level: {new_stock}"
            if new_stock < 0:
                stock_status += f" (Backorder: {abs(new_stock)} units)"
            product_name = branch_product.catalog_product.name if branch_product.catalog_product else "Unknown Product"
            flash(f'Successfully {action} stock for {product_name}. {stock_status}', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to adjust stock: {str(e)}', 'error')
            print(f"Error adjusting stock: {str(e)}")
    
    # Get accessible products for the form
    accessible_branch_ids = get_user_accessible_branch_ids()
    products_query = BranchProduct.query
    if accessible_branch_ids:
        products_query = products_query.filter(BranchProduct.branchid.in_(accessible_branch_ids))
    products = products_query.order_by(BranchProduct.catalog_product.has(ProductCatalog.name)).all()
    
    return render_template('stock_adjustment.html', products=products)

# Helper functions for PDF generation
def format_currency(amount):
    """Format currency for PDFs"""
    return f"KSh {amount:,.2f}"

def format_quantity(quantity):
    """Format quantity for PDFs - remove unnecessary decimal places"""
    if quantity is None:
        return "0"
    qty = float(quantity)
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.2f}".rstrip('0').rstrip('.')

def create_delivery_note_pdf_a4(order, user_data, output_path):
    """
    Create a professional delivery note PDF (A4 size)
    output_path can be a file path (string) or BytesIO object
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from datetime import datetime
    import pytz
    
    # Set timezone to East Africa Time
    EAT = pytz.timezone('Africa/Nairobi')
    
    # Create PDF buffer
    if isinstance(output_path, str):
        # If output_path is a string, create a file
        doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    else:
        # If output_path is BytesIO, use it directly
        doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#2c3e50')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=20,
        textColor=colors.HexColor('#34495e')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=12
    )
    
    # Recreate the ABZ Hardware letterhead manually
    
    # Try to load the logo for the left side
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
        if os.path.exists(logo_path):
            logo_image = Image(logo_path, width=1.5*inch, height=1*inch)
            logo_cell = logo_image
        else:
            # Fallback to text if logo not found
            logo_cell = Paragraph('''
            <para align=left>
            <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
            <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
            <b><font size=14 color="#1a365d">LIMITED</font></b>
            </para>
            ''', normal_style)
    except Exception as e:
        print(f"Error loading logo: {e}")
        # Fallback to text if logo fails to load
        logo_cell = Paragraph('''
        <para align=left>
        <b><font size=24 color="#1a365d">🔧ABZ</font></b><br/>
        <b><font size=16 color="#f4b942">HARDWARE</font></b><br/>
        <b><font size=14 color="#1a365d">LIMITED</font></b>
        </para>
        ''', normal_style)
    
    # Create the letterhead table for proper layout
    letterhead_data = [[
        # Left side - Logo Image
        logo_cell,
        
        # Right side - Contact Information
        Paragraph('''
        <para align=right>
        <b><font size=11 color="#1a365d">Kombo Munyiri Road,</font></b><br/>
        <b><font size=11 color="#1a365d">Gikomba, Nairobi, Kenya</font></b><br/>
        <font size=9 color="#666666">0711 732 341 or 0725 000 055</font><br/>
        <font size=9 color="#666666">info@abzhardware.co.ke</font><br/>
        <font size=9 color="#666666">www.abzhardware.co.ke</font>
        </para>
        ''', normal_style)
    ]]
    
    # Create letterhead table
    letterhead_table = Table(letterhead_data, colWidths=[3.5*inch, 3.5*inch])
    letterhead_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
    ]))
    
    elements.append(letterhead_table)
    elements.append(Spacer(1, 10))
    
    # Add the colored line separator (yellow)
    separator_data = [[""]]
    separator_table = Table(separator_data, colWidths=[7*inch], rowHeights=[0.05*inch])
    separator_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4b942')),  # Yellow color
    ]))
    
    elements.append(separator_table)
    elements.append(Spacer(1, 30))
    
    # Delivery Note Title
    elements.append(Paragraph("DELIVERY NOTE", title_style))
    elements.append(Spacer(1, 10))
    
    # Delivery Note Details Section
    delivery_note_details = f"""
    <b>Delivery Note Number:</b> DN-{order.id:06d}<br/>
    <b>Order Number:</b> ORD-{order.id:06d}<br/>
    <b>Date:</b> {order.created_at.strftime('%B %d, %Y') if order.created_at else 'N/A'}<br/>
    <b>Branch:</b> {order.branch.name if order.branch else 'N/A'}<br/>
    """
    elements.append(Paragraph(delivery_note_details, normal_style))
    elements.append(Spacer(1, 20))
    
    # Items Table
    if order.order_items:
        elements.append(Paragraph("ITEMS FOR DELIVERY", heading_style))
        
        # Table data - No, Product Name - Code, Quantity
        data = [['No', 'Product Name', 'Quantity']]
        
        # Create a style for product names that allows wrapping
        product_name_style = ParagraphStyle(
            'ProductName',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=0,
            spaceBefore=0,
            leading=13,  # Line spacing for multi-line text
            alignment=0,  # Left alignment
            fontName='Helvetica'
        )
        
        for idx, item in enumerate(order.order_items, 1):
            # Get product name
            if item.product_name:
                product_name = item.product_name
            elif item.branch_product and item.branch_product.catalog_product:
                product_name = item.branch_product.catalog_product.name
            else:
                product_name = 'N/A'
            
            # Get product code
            product_code = ''
            if item.branch_product and item.branch_product.catalog_product:
                product_code = item.branch_product.catalog_product.productcode or ''
            
            # Combine product name and code
            if product_code:
                product_display = f"{product_name} - {product_code}"
            else:
                product_display = product_name
            
            quantity = item.quantity
            
            # Format quantity
            quantity_text = format_quantity(quantity)
            
            data.append([
                str(idx),
                Paragraph(product_display.upper(), product_name_style),
                quantity_text
            ])
        
        # Create table with 3 columns
        table = Table(data, colWidths=[0.6*inch, 5.4*inch, 1*inch])
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#4a5568')),
            
            # Alternating row colors
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.white]),
            
            # Alignment adjustments
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # No column center
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Product Name left
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # Quantity center
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 30))
    else:
        elements.append(Paragraph("No items in this delivery note.", normal_style))
        elements.append(Spacer(1, 30))
    
    # Signature Section
    elements.append(Spacer(1, 50))
    
    signature_data = [
        ['Prepared By:', 'Received By:'],
        ['', ''],
        ['', ''],
        [f'Name: {user_data.firstname} {user_data.lastname}', 'Name: _______________________'],
        [f'Date: {datetime.now(EAT).strftime("%B %d, %Y")}', 'Date: _______________________'],
        ['Signature: _______________________', 'Signature: _______________________']
    ]
    
    signature_table = Table(signature_data, colWidths=[3.5*inch, 3.5*inch])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#cbd5e0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(signature_table)
    elements.append(Spacer(1, 20))
    
    # Footer
    footer_text = f"""
    <para align=center>
    <font size=8 color="#95a5a6">
    Generated on {datetime.now(EAT).strftime('%B %d, %Y at %I:%M %p')} by {user_data.firstname} {user_data.lastname}<br/>
    This is a computer-generated document and does not require a signature.<br/>
    Please inspect all items upon delivery. Report any discrepancies immediately.
    </font>
    </para>
    """
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    return output_path

@app.route('/order/<int:order_id>/delivery-note')
@cashier_required
def generate_delivery_note_from_order(order_id):
    """Generate delivery note PDF for an order"""
    from io import BytesIO
    
    order = Order.query.get_or_404(order_id)
    
    # Check if user has access to this order's branch
    if not current_user.has_branch_access(order.branchid):
        flash('Access denied. You do not have permission to generate this delivery note.', 'error')
        return redirect(url_for('orders'))
    
    # Create PDF in memory
    buffer = BytesIO()
    create_delivery_note_pdf_a4(order, current_user, buffer)
    buffer.seek(0)
    
    # Generate filename
    filename = f"delivery_note_DN-{order.id:06d}.pdf"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

@app.route('/deliveries/<int:delivery_id>/delivery-note/preview')
@cashier_required
def delivery_note_preview(delivery_id):
    """Show delivery note preview page"""
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    if not current_user.has_branch_access(delivery.order.branchid):
        flash('Access denied. You do not have permission to view this delivery note.', 'error')
        return redirect(url_for('deliveries'))
    
    return render_template('delivery_note_preview.html', delivery=delivery)

@app.route('/deliveries/<int:delivery_id>/delivery-note')
@app.route('/deliveries/<int:delivery_id>/delivery-note/<action>')
@cashier_required
def generate_delivery_note(delivery_id, action='download'):
    """Generate delivery note PDF for a delivery"""
    from io import BytesIO
    
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    if not current_user.has_branch_access(delivery.order.branchid):
        flash('Access denied. You do not have permission to generate this delivery note.', 'error')
        return redirect(url_for('deliveries'))
    
    # Create PDF in memory using the order from the delivery
    buffer = BytesIO()
    create_delivery_note_pdf_a4(delivery.order, current_user, buffer)
    buffer.seek(0)
    
    # Generate filename
    filename = f"delivery_note_DN-{delivery.id:06d}.pdf"
    
    # Return as download or inline view
    if action == 'view':
        return send_file(
            buffer,
            as_attachment=False,
            download_name=filename,
            mimetype='application/pdf'
        )
    else:
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

@app.route('/payment/<int:payment_id>/receipt/preview')
@cashier_required
def receipt_preview(payment_id):
    """Show receipt preview page"""
    payment = Payment.query.get_or_404(payment_id)
    
    # Check if user has access to this payment's order branch
    if not current_user.has_branch_access(payment.order.branchid):
        flash('Access denied. You do not have permission to view this receipt.', 'error')
        return redirect(url_for('payments'))
    
    return render_template('receipt_preview.html', payment=payment)

@app.route('/payment/<int:payment_id>/receipt')
@app.route('/payment/<int:payment_id>/receipt/<action>')
@cashier_required
def generate_receipt(payment_id, action='view'):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame,
        Paragraph, Spacer, Table, TableStyle, Image
    )
    from io import BytesIO
    import os

    payment = Payment.query.get_or_404(payment_id)
    
    # Check if user has access to this payment's order branch
    if not current_user.has_branch_access(payment.order.branchid):
        flash('Access denied. You do not have permission to generate this receipt.', 'error')
        return redirect(url_for('payments'))

    def format_currency(amount):
        return f"KSh{amount:,.2f}"

    buffer = BytesIO()
    page_width = 210  # safe width for 80mm printer (~74mm printable area)
    
    # Create a single page with very large height to ensure all content fits
    # This prevents page breaks and creates one continuous receipt
    doc = BaseDocTemplate(buffer, pagesize=(page_width, 3000),
                          leftMargin=10, rightMargin=10, topMargin=10, bottomMargin=10)
    
    # Create a frame that spans the entire page height
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    
    # Custom page template that prevents page breaks
    def onPage(canvas, doc):
        # This ensures only one page is created
        pass
    
    template = PageTemplate(id='receipt', frames=[frame], onPage=onPage)
    doc.addPageTemplates([template])
    
    # Disable page breaks and set to single page mode
    doc.allowSplitting = 0
    doc.pageBreakBefore = 0

    story = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=12, alignment=1, spaceAfter=1)   # tighter
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=10, alignment=1, spaceAfter=4)  # reduced
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, alignment=0, spaceAfter=4, fontName="Helvetica-Bold")
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=8, alignment=0, spaceAfter=2)
    center_style = ParagraphStyle('Center', parent=styles['Normal'], fontSize=8, alignment=1, spaceAfter=2)

    # Logo (if available)
    logo_path = os.path.join(app.static_folder, 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=50, height=25)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 4))
        except:
            pass

    # Header text (tighter spacing)
    story.append(Paragraph("ABZ HARDWARE", title_style))
    story.append(Paragraph("Acknowledgement Receipt", subtitle_style))

    # Only Date
    story.append(Paragraph(f"<b>Date:</b> {(payment.created_at + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')}", normal_style))
    story.append(Spacer(1, 6))

    # Payment Details
    story.append(Paragraph("PAYMENT DETAILS", header_style))
    story.append(Paragraph(f"Method: {payment.payment_method.title() if payment.payment_method else 'N/A'}", normal_style))
    story.append(Paragraph(f"Amount: {format_currency(payment.amount)}", normal_style))
    if payment.reference_number:
        story.append(Paragraph(f"Ref: {payment.reference_number}", normal_style))
    story.append(Spacer(1, 6))

    # Order Items
    order = getattr(payment, 'order', None)
    if order and order.order_items:
        story.append(Paragraph("ORDER ITEMS", header_style))
        story.append(Spacer(1, 4))

        data = [["Product", "Qty", "Price", "Total"]]
        for item in order.order_items:
            price = float(item.final_price or item.original_price or 0)
            total = float(item.quantity) * price
            # Use product_name from orderdetails if product relationship is null
            if item.branch_product and item.branch_product.catalog_product:
                product_name = item.branch_product.catalog_product.name
            else:
                product_name = item.product_name or "N/A"

            # Wrapping for product names
            data.append([
                Paragraph(product_name, normal_style),
                str(item.quantity),
                f"{price:,.2f}",
                f"{total:,.2f}"
            ])

        table = Table(data, colWidths=[85, 25, 45, 45])
        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ALIGN', (1,1), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
        ]))
        table.hAlign = 'CENTER'
        story.append(table)
        story.append(Spacer(1, 6))

        # Total
        total_amount = sum(float(item.quantity) * float(item.final_price or item.original_price or 0) for item in order.order_items)
        story.append(Paragraph(f"<b>TOTAL: {format_currency(total_amount)}</b>", header_style))
        story.append(Spacer(1, 10))

        # Served By (firstname only)
        if order.user:
            sales_person = f"{order.user.firstname}"
            story.append(Paragraph(f"Served By: {sales_person}", normal_style))
            story.append(Spacer(1, 6))

    # Company Contact Info
    story.append(Paragraph("Phone: 0725000055 / 0711732341", center_style))
    story.append(Paragraph("Email: info@abzhardware.co.ke", center_style))
    story.append(Paragraph("Website: www.abzhardware.co.ke", center_style))
    story.append(Spacer(1, 6))

    # Footer
    story.append(Paragraph("Thank you for your business!", center_style))
    story.append(Paragraph("ABZ Hardware", center_style))
    story.append(Paragraph("Quality Hardware Solutions", center_style))

    # Build the document
    doc.build(story)

    pdf = buffer.getvalue()
    buffer.close()

    from flask import make_response
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    
    if action == 'download':
        response.headers['Content-Disposition'] = f'attachment; filename=receipt_{payment.id}.pdf'
    else:
        # For viewing, show inline
        response.headers['Content-Disposition'] = f'inline; filename=receipt_{payment.id}.pdf'
    
    return response





# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

# Expense V2 Management Routes (New Flow)
@app.route('/expenses-v2')
@cashier_required
def expenses_v2():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    payment_status_filter = request.args.get('payment_status', 'all')
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Build query with branch filtering
    query = ExpenseV2.query
    
    # Filter by accessible branches
    if accessible_branch_ids:
        query = query.filter(ExpenseV2.branch_id.in_(accessible_branch_ids))
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    # Hide restricted categories (salaries only) from cashiers
    query = query.filter(~ExpenseV2.category.in_(['salaries']))
    
    # Get expenses with pagination
    expenses = query.order_by(ExpenseV2.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get unique categories for filter dropdown
    categories = db.session.query(ExpenseV2.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('expenses_v2.html', 
                         expenses=expenses, 
                         status_filter=status_filter,
                         category_filter=category_filter,
                         payment_status_filter=payment_status_filter,
                         categories=categories)

@app.route('/expenses-v2/add', methods=['GET', 'POST'])
@cashier_required
def add_expense_v2():
    if request.method == 'POST':
        try:
            # Get accessible branch IDs for current user
            accessible_branch_ids = get_user_accessible_branch_ids()
            
            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            amount = request.form.get('amount')
            category = request.form.get('category')
            expense_date = request.form.get('expense_date')
            branch_id = request.form.get('branch_id')
            
            # Process uploaded receipt files
            receipt_urls = []
            if 'receipt_files' in request.files:
                files = request.files.getlist('receipt_files')
                for file in files:
                    if file and file.filename:
                        # Upload to Cloudinary
                        uploaded_url = upload_to_cloudinary(file)
                        if uploaded_url:
                            receipt_urls.append(uploaded_url)
                        else:
                            flash(f'Failed to upload file: {file.filename}', 'error')
            
            # Validate required fields
            if not all([title, amount, category, expense_date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('add_expense_v2'))
            
            # Validate branch access
            if branch_id:
                branch_id = int(branch_id)
                if branch_id not in accessible_branch_ids:
                    flash('You do not have access to this branch.', 'error')
                    return redirect(url_for('add_expense_v2'))
            else:
                # If no branch selected and user has access to multiple branches, require selection
                if len(accessible_branch_ids) > 1:
                    flash('Please select a branch.', 'error')
                    return redirect(url_for('add_expense_v2'))
                elif len(accessible_branch_ids) == 1:
                    branch_id = accessible_branch_ids[0]
                else:
                    branch_id = None
            
            # Create new expense
            expense = ExpenseV2(
                title=title,
                description=description,
                amount=float(amount),
                category=category,
                expense_date=datetime.strptime(expense_date, '%Y-%m-%d').date(),
                receipt_urls=receipt_urls if receipt_urls else None,
                branch_id=branch_id,
                user_id=current_user.id,
                status='pending'
            )
            
            db.session.add(expense)
            db.session.commit()
            
            flash('Expense added successfully!', 'success')
            return redirect(url_for('view_expense_v2', expense_id=expense.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('add_expense_v2'))
    
    # GET request - show form
    # Get accessible branches for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    accessible_branches = current_user.get_accessible_branches()
    
    return render_template('add_expense_v2.html', branches=accessible_branches)

@app.route('/expenses-v2/<int:expense_id>')
@cashier_required
def view_expense_v2(expense_id):
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get expense with access control
    expense = ExpenseV2.query.get_or_404(expense_id)
    
    # Check if user has access to this expense's branch
    if expense.branch_id and expense.branch_id not in accessible_branch_ids:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    # Hide restricted categories (salaries only) from cashiers
    if expense.category in ['salaries']:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    # Get payments for this expense
    payments = ExpensePayment.query.filter_by(expense_id=expense_id).order_by(ExpensePayment.created_at.desc()).all()
    
    return render_template('view_expense_v2.html', expense=expense, payments=payments)

@app.route('/expenses-v2/<int:expense_id>/edit', methods=['GET', 'POST'])
@cashier_required
def edit_expense_v2(expense_id):
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get expense with access control
    expense = ExpenseV2.query.get_or_404(expense_id)
    
    # Check if user has access to this expense's branch
    if expense.branch_id and expense.branch_id not in accessible_branch_ids:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    # Hide restricted categories (salaries only) from cashiers
    if expense.category in ['salaries']:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    # Only allow editing if expense is pending
    if expense.status != 'pending':
        flash('You can only edit pending expenses.', 'error')
        return redirect(url_for('view_expense_v2', expense_id=expense_id))
    
    if request.method == 'POST':
        try:
            # Check if this is a receipt deletion request
            action = request.form.get('action')
            if action == 'delete_receipt':
                receipt_url = request.form.get('receipt_url')
                if receipt_url and receipt_url in expense.receipt_list:
                    # Remove the receipt from the list
                    updated_receipts = [url for url in expense.receipt_list if url != receipt_url]
                    expense.receipt_urls = updated_receipts if updated_receipts else None
                    
                    # Delete from Cloudinary
                    try:
                        # Extract public_id from Cloudinary URL
                        if 'cloudinary.com' in receipt_url:
                            public_id = receipt_url.split('/')[-1].split('.')[0]
                            delete_from_cloudinary(public_id)
                    except Exception as e:
                        print(f"Failed to delete from Cloudinary: {e}")
                    
                    db.session.commit()
                    flash('Receipt deleted successfully!', 'success')
                else:
                    flash('Receipt not found.', 'error')
                
                return redirect(url_for('edit_expense_v2', expense_id=expense_id))
            
            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            amount = request.form.get('amount')
            category = request.form.get('category')
            expense_date = request.form.get('expense_date')
            branch_id = request.form.get('branch_id')
            
            # Process uploaded receipt files
            receipt_urls = []
            if 'receipt_files' in request.files:
                files = request.files.getlist('receipt_files')
                for file in files:
                    if file and file.filename:
                        # Upload to Cloudinary
                        uploaded_url = upload_to_cloudinary(file)
                        if uploaded_url:
                            receipt_urls.append(uploaded_url)
                        else:
                            flash(f'Failed to upload file: {file.filename}', 'error')
            
            # If no new files uploaded, keep existing URLs
            if not receipt_urls:
                receipt_urls = expense.receipt_list
            
            # Validate required fields
            if not all([title, amount, category, expense_date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('edit_expense_v2', expense_id=expense_id))
            
            # Validate branch access
            if branch_id:
                branch_id = int(branch_id)
                if branch_id not in accessible_branch_ids:
                    flash('You do not have access to this branch.', 'error')
                    return redirect(url_for('edit_expense_v2', expense_id=expense_id))
            else:
                if len(accessible_branch_ids) > 1:
                    flash('Please select a branch.', 'error')
                    return redirect(url_for('edit_expense_v2', expense_id=expense_id))
                elif len(accessible_branch_ids) == 1:
                    branch_id = accessible_branch_ids[0]
                else:
                    branch_id = None
            
            # Update expense
            expense.title = title
            expense.description = description
            expense.amount = float(amount)
            expense.category = category
            expense.expense_date = datetime.strptime(expense_date, '%Y-%m-%d').date()
            expense.receipt_urls = receipt_urls if receipt_urls else None
            expense.branch_id = branch_id
            expense.updated_at = datetime.now()
            
            db.session.commit()
            
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('view_expense_v2', expense_id=expense_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'error')
            return redirect(url_for('edit_expense_v2', expense_id=expense_id))
    
    # GET request - show form
    accessible_branches = current_user.get_accessible_branches()
    
    return render_template('edit_expense_v2.html', expense=expense, branches=accessible_branches)

@app.route('/expenses-v2/<int:expense_id>/payments/add', methods=['GET', 'POST'])
@cashier_required
def add_expense_payment(expense_id):
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get expense with access control
    expense = ExpenseV2.query.get_or_404(expense_id)
    
    # Check if user has access to this expense's branch
    if expense.branch_id and expense.branch_id not in accessible_branch_ids:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    # Hide restricted categories (salaries only) from cashiers
    if expense.category in ['salaries']:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses_v2'))
    
    if request.method == 'POST':
        try:
            # Get form data
            amount = request.form.get('amount')
            payment_method = request.form.get('payment_method')
            payment_date = request.form.get('payment_date')
            payment_reference = request.form.get('payment_reference')
            notes = request.form.get('notes')
            
            # Validate required fields
            if not all([amount, payment_method, payment_date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('add_expense_payment', expense_id=expense_id))
            
            # Create new payment
            payment = ExpensePayment(
                expense_id=expense_id,
                amount=float(amount),
                payment_method=payment_method,
                payment_date=datetime.strptime(payment_date, '%Y-%m-%d').date(),
                payment_reference=payment_reference,
                notes=notes,
                user_id=current_user.id,
                status='completed'  # Auto-complete payments for cashiers
            )
            
            db.session.add(payment)
            db.session.commit()
            
            flash('Payment added successfully!', 'success')
            return redirect(url_for('view_expense_v2', expense_id=expense_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding payment: {str(e)}', 'error')
            return redirect(url_for('add_expense_payment', expense_id=expense_id))
    
    # GET request - show form
    return render_template('add_expense_payment.html', expense=expense)

# Expense Management Routes (Old System)
@app.route('/expenses')
@cashier_required
def expenses():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Build query with branch filtering
    query = Expense.query
    
    # Filter by accessible branches
    if accessible_branch_ids:
        query = query.filter(Expense.branch_id.in_(accessible_branch_ids))
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    # Hide restricted categories (rent and salaries) from cashiers
    query = query.filter(~Expense.category.in_(['rent', 'salaries']))
    
    # Get expenses with pagination
    expenses = query.order_by(Expense.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get unique categories for filter dropdown
    categories = db.session.query(Expense.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('expenses.html', 
                         expenses=expenses, 
                         status_filter=status_filter,
                         category_filter=category_filter,
                         categories=categories)

@app.route('/expenses/add', methods=['GET', 'POST'])
@cashier_required
def add_expense():
    if request.method == 'POST':
        try:
            # Get accessible branch IDs for current user
            accessible_branch_ids = get_user_accessible_branch_ids()
            
            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            amount = request.form.get('amount')
            category = request.form.get('category')
            expense_date = request.form.get('expense_date')
            payment_method = request.form.get('payment_method')
            branch_id = request.form.get('branch_id')
            
            # Validate required fields
            if not all([title, amount, category, expense_date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('add_expense'))
            
            # Validate branch access
            if branch_id:
                branch_id = int(branch_id)
                if branch_id not in accessible_branch_ids:
                    flash('You do not have access to this branch.', 'error')
                    return redirect(url_for('add_expense'))
            else:
                # If no branch selected and user has access to multiple branches, require selection
                if len(accessible_branch_ids) > 1:
                    flash('Please select a branch.', 'error')
                    return redirect(url_for('add_expense'))
                elif len(accessible_branch_ids) == 1:
                    branch_id = accessible_branch_ids[0]
                else:
                    branch_id = None
            
            # Create new expense
            expense = Expense(
                title=title,
                description=description,
                amount=float(amount),
                category=category,
                expense_date=datetime.strptime(expense_date, '%Y-%m-%d').date(),
                payment_method=payment_method,
                branch_id=branch_id,
                user_id=current_user.id,
                status='pending'
            )
            
            db.session.add(expense)
            db.session.commit()
            
            flash('Expense added successfully!', 'success')
            return redirect(url_for('expenses'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('add_expense'))
    
    # GET request - show form
    # Get accessible branches for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    accessible_branches = current_user.get_accessible_branches()
    
    return render_template('add_expense.html', branches=accessible_branches)

@app.route('/expenses/<int:expense_id>')
@cashier_required
def view_expense(expense_id):
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get expense with access control
    expense = Expense.query.get_or_404(expense_id)
    
    # Check if user has access to this expense's branch
    if expense.branch_id and expense.branch_id not in accessible_branch_ids:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses'))
    
    # Hide restricted categories (rent and salaries) from cashiers
    if expense.category in ['rent', 'salaries']:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses'))
    
    return render_template('view_expense.html', expense=expense)

@app.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
@cashier_required
def edit_expense(expense_id):
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Get expense with access control
    expense = Expense.query.get_or_404(expense_id)
    
    # Check if user has access to this expense's branch
    if expense.branch_id and expense.branch_id not in accessible_branch_ids:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses'))
    
    # Hide restricted categories (rent and salaries) from cashiers
    if expense.category in ['rent', 'salaries']:
        flash('You do not have access to this expense.', 'error')
        return redirect(url_for('expenses'))
    
    # Only allow editing if expense is pending
    if expense.status != 'pending':
        flash('You can only edit pending expenses.', 'error')
        return redirect(url_for('view_expense', expense_id=expense_id))
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            amount = request.form.get('amount')
            category = request.form.get('category')
            expense_date = request.form.get('expense_date')
            payment_method = request.form.get('payment_method')
            branch_id = request.form.get('branch_id')
            
            # Validate required fields
            if not all([title, amount, category, expense_date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('edit_expense', expense_id=expense_id))
            
            # Validate branch access
            if branch_id:
                branch_id = int(branch_id)
                if branch_id not in accessible_branch_ids:
                    flash('You do not have access to this branch.', 'error')
                    return redirect(url_for('edit_expense', expense_id=expense_id))
            else:
                if len(accessible_branch_ids) > 1:
                    flash('Please select a branch.', 'error')
                    return redirect(url_for('edit_expense', expense_id=expense_id))
                elif len(accessible_branch_ids) == 1:
                    branch_id = accessible_branch_ids[0]
                else:
                    branch_id = None
            
            # Update expense
            expense.title = title
            expense.description = description
            expense.amount = float(amount)
            expense.category = category
            expense.expense_date = datetime.strptime(expense_date, '%Y-%m-%d').date()
            expense.payment_method = payment_method
            expense.branch_id = branch_id
            expense.updated_at = datetime.now()
            
            db.session.commit()
            
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('view_expense', expense_id=expense_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'error')
            return redirect(url_for('edit_expense', expense_id=expense_id))
    
    # GET request - show form
    accessible_branches = current_user.get_accessible_branches()
    
    return render_template('edit_expense.html', expense=expense, branches=accessible_branches)

# ==================== DELIVERY MANAGEMENT ====================

@app.route('/deliveries')
@cashier_required
def deliveries():
    """List all deliveries with filters and pagination"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    branch_filter = request.args.get('branch', 'all')
    
    # Get accessible branch IDs for current user
    accessible_branch_ids = get_user_accessible_branch_ids()
    
    # Base query with joins
    query = db.session.query(Delivery).join(Order).join(Branch)
    
    # Filter by accessible branches
    if accessible_branch_ids:
        query = query.filter(Order.branchid.in_(accessible_branch_ids))
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter(Delivery.delivery_status == status_filter)
    
    if branch_filter != 'all':
        query = query.filter(Order.branchid == branch_filter)
    
    # Get deliveries with pagination
    deliveries = query.order_by(Delivery.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get unique statuses for filter dropdown
    statuses = ['pending', 'in_transit', 'delivered', 'cancelled', 'failed']
    
    # Get accessible branches for filter dropdown
    accessible_branches = current_user.get_accessible_branches()
    
    return render_template('deliveries.html', deliveries=deliveries, 
                         statuses=statuses, branches=accessible_branches,
                         current_status=status_filter, current_branch=branch_filter)

@app.route('/deliveries/create', methods=['GET', 'POST'])
@cashier_required
def create_delivery():
    """Create a new delivery for an order"""
    if request.method == 'POST':
        try:
            # Get form data
            order_id = request.form.get('order_id')
            delivery_amount = request.form.get('delivery_amount')
            delivery_location = request.form.get('delivery_location')
            customer_phone = request.form.get('customer_phone')
            agreed_delivery_time = request.form.get('agreed_delivery_time')
            notes = request.form.get('notes')
            
            # Validate required fields
            if not all([order_id, delivery_amount, delivery_location, customer_phone]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('create_delivery'))
            
            # Check if order exists and user has access
            order = Order.query.get(order_id)
            if not order:
                flash('Order not found.', 'error')
                return redirect(url_for('create_delivery'))
            
            accessible_branch_ids = get_user_accessible_branch_ids()
            if order.branchid not in accessible_branch_ids:
                flash('You do not have access to this order.', 'error')
                return redirect(url_for('create_delivery'))
            
            # Check if delivery already exists for this order
            existing_delivery = Delivery.query.filter_by(order_id=order_id).first()
            if existing_delivery:
                flash('A delivery already exists for this order.', 'error')
                return redirect(url_for('create_delivery'))
            
            # Create delivery
            delivery = Delivery(
                order_id=int(order_id),
                delivery_amount=float(delivery_amount),
                delivery_location=delivery_location,
                customer_phone=customer_phone,
                agreed_delivery_time=datetime.strptime(agreed_delivery_time, '%Y-%m-%dT%H:%M') if agreed_delivery_time else None,
                notes=notes,
                delivery_status='pending',
                payment_status='pending'
            )
            
            db.session.add(delivery)
            db.session.commit()
            
            flash('Delivery created successfully!', 'success')
            return redirect(url_for('view_delivery', delivery_id=delivery.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating delivery: {str(e)}', 'error')
            return redirect(url_for('create_delivery'))
    
    # GET request - show form
    # Get orders that don't have deliveries yet and user has access to
    accessible_branch_ids = get_user_accessible_branch_ids()
    orders_query = Order.query.filter_by(approvalstatus=True)  # Only approved orders
    
    if accessible_branch_ids:
        orders_query = orders_query.filter(Order.branchid.in_(accessible_branch_ids))
    
    # Exclude orders that already have deliveries
    orders_with_deliveries = db.session.query(Delivery.order_id).subquery()
    orders_query = orders_query.filter(~Order.id.in_(orders_with_deliveries))
    
    orders = orders_query.order_by(Order.created_at.desc()).all()
    
    return render_template('create_delivery.html', orders=orders)

@app.route('/deliveries/<int:delivery_id>')
@cashier_required
def view_delivery(delivery_id):
    """View delivery details"""
    # Get delivery with access control
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    accessible_branch_ids = get_user_accessible_branch_ids()
    if delivery.order.branchid not in accessible_branch_ids:
        flash('You do not have access to this delivery.', 'error')
        return redirect(url_for('deliveries'))
    
    # Get delivery payments
    payments = DeliveryPayment.query.filter_by(delivery_id=delivery_id).order_by(DeliveryPayment.created_at.desc()).all()
    
    return render_template('view_delivery.html', delivery=delivery, payments=payments)

@app.route('/deliveries/<int:delivery_id>/edit', methods=['GET', 'POST'])
@cashier_required
def edit_delivery(delivery_id):
    """Edit delivery details"""
    # Get delivery with access control
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    accessible_branch_ids = get_user_accessible_branch_ids()
    if delivery.order.branchid not in accessible_branch_ids:
        flash('You do not have access to this delivery.', 'error')
        return redirect(url_for('deliveries'))
    
    # Only allow editing if delivery is pending or in_transit
    if delivery.delivery_status not in ['pending', 'in_transit']:
        flash('You can only edit pending or in-transit deliveries.', 'error')
        return redirect(url_for('view_delivery', delivery_id=delivery_id))
    
    if request.method == 'POST':
        try:
            # Get form data
            delivery_amount = request.form.get('delivery_amount')
            delivery_location = request.form.get('delivery_location')
            customer_phone = request.form.get('customer_phone')
            agreed_delivery_time = request.form.get('agreed_delivery_time')
            delivery_status = request.form.get('delivery_status')
            notes = request.form.get('notes')
            
            # Validate required fields
            if not all([delivery_amount, delivery_location, customer_phone]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('edit_delivery', delivery_id=delivery_id))
            
            # Update delivery
            delivery.delivery_amount = float(delivery_amount)
            delivery.delivery_location = delivery_location
            delivery.customer_phone = customer_phone
            delivery.agreed_delivery_time = datetime.strptime(agreed_delivery_time, '%Y-%m-%dT%H:%M') if agreed_delivery_time else None
            delivery.delivery_status = delivery_status
            delivery.notes = notes
            delivery.updated_at = datetime.now()
            
            db.session.commit()
            
            flash('Delivery updated successfully!', 'success')
            return redirect(url_for('view_delivery', delivery_id=delivery_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating delivery: {str(e)}', 'error')
            return redirect(url_for('edit_delivery', delivery_id=delivery_id))
    
    # GET request - show form
    return render_template('edit_delivery.html', delivery=delivery)

@app.route('/deliveries/<int:delivery_id>/update-status', methods=['POST'])
@cashier_required
def update_delivery_status(delivery_id):
    """Update delivery status"""
    # Get delivery with access control
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    accessible_branch_ids = get_user_accessible_branch_ids()
    if delivery.order.branchid not in accessible_branch_ids:
        flash('You do not have access to this delivery.', 'error')
        return redirect(url_for('deliveries'))
    
    try:
        new_status = request.form.get('status')
        if new_status not in ['pending', 'in_transit', 'delivered', 'cancelled', 'failed']:
            flash('Invalid status.', 'error')
            return redirect(url_for('view_delivery', delivery_id=delivery_id))
        
        delivery.delivery_status = new_status
        delivery.updated_at = datetime.now()
        
        db.session.commit()
        
        flash(f'Delivery status updated to {new_status.replace("_", " ").title()}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating delivery status: {str(e)}', 'error')
    
    return redirect(url_for('view_delivery', delivery_id=delivery_id))

@app.route('/deliveries/<int:delivery_id>/payments/add', methods=['GET', 'POST'])
@cashier_required
def add_delivery_payment(delivery_id):
    """Add payment for a delivery"""
    # Get delivery with access control
    delivery = Delivery.query.get_or_404(delivery_id)
    
    # Check if user has access to this delivery's order branch
    accessible_branch_ids = get_user_accessible_branch_ids()
    if delivery.order.branchid not in accessible_branch_ids:
        flash('You do not have access to this delivery.', 'error')
        return redirect(url_for('deliveries'))
    
    if request.method == 'POST':
        try:
            # Get form data
            amount = request.form.get('amount')
            payment_method = request.form.get('payment_method')
            payment_status = request.form.get('payment_status')
            transaction_id = request.form.get('transaction_id')
            reference_number = request.form.get('reference_number')
            notes = request.form.get('notes')
            payment_date = request.form.get('payment_date')
            
            # Validate required fields
            if not all([amount, payment_method, payment_status]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('add_delivery_payment', delivery_id=delivery_id))
            
            # Create delivery payment
            payment = DeliveryPayment(
                delivery_id=delivery_id,
                user_id=current_user.id,
                amount=float(amount),
                payment_method=payment_method,
                payment_status=payment_status,
                transaction_id=transaction_id,
                reference_number=reference_number,
                notes=notes,
                payment_date=datetime.strptime(payment_date, '%Y-%m-%dT%H:%M') if payment_date else None
            )
            
            db.session.add(payment)
            
            # Update delivery payment status based on payments
            total_paid = db.session.query(db.func.sum(DeliveryPayment.amount)).filter(
                DeliveryPayment.delivery_id == delivery_id,
                DeliveryPayment.payment_status == 'completed'
            ).scalar() or 0
            
            if total_paid >= delivery.delivery_amount:
                delivery.payment_status = 'paid'
            elif total_paid > 0:
                delivery.payment_status = 'partial'
            else:
                delivery.payment_status = 'pending'
            
            db.session.commit()
            
            flash('Delivery payment added successfully!', 'success')
            return redirect(url_for('view_delivery', delivery_id=delivery_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding delivery payment: {str(e)}', 'error')
            return redirect(url_for('add_delivery_payment', delivery_id=delivery_id))
    
    # GET request - show form
    return render_template('add_delivery_payment.html', delivery=delivery)

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
