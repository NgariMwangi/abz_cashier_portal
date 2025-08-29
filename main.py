from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Branch, Product, Order, OrderItem, Payment, StockTransaction, Supplier, PurchaseOrder, PurchaseOrderItem, Quotation, QuotationItem, SubCategory
from datetime import datetime, timedelta
import os
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from functools import wraps
app = Flask(__name__)
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
    
    # Get pending orders count
    pending_orders_count = Order.query.filter_by(approvalstatus=False).count()
    
    # Get today's orders count
    today_orders_count = Order.query.filter(
        func.date(Order.created_at) == today
    ).count()
    
    # Get pending payments count (all payments are now completed, so this will be 0)
    pending_payments_count = 0
    
    # Get today's revenue
    today_revenue = db.session.query(func.sum(Payment.amount)).filter(
        func.date(Payment.created_at) == today,
        Payment.payment_status == 'completed'
    ).scalar() or 0
    
    # Get recent pending orders
    recent_orders = Order.query.filter_by(approvalstatus=False).order_by(
        Order.created_at.desc()
    ).limit(5).all()
    
    # Calculate total amount and payment status for each recent order
    for order in recent_orders:
        total_amount = 0
        if order.order_items:
            for item in order.order_items:
                price = item.final_price or item.original_price or 0
                total_amount += item.quantity * price
        order.total_amount = total_amount
        
        # Calculate payment status
        if total_amount == 0:
            order.payment_status = 'No Items'
        else:
            total_payments = db.session.query(func.sum(Payment.amount)).filter(
                Payment.orderid == order.id,
                Payment.payment_status == 'completed'
            ).scalar() or 0
            
            # Convert to float for comparison
            total_payments_float = float(total_payments) if total_payments else 0.0
            total_amount_float = float(total_amount) if total_amount else 0.0
            
            if total_payments_float >= total_amount_float:
                order.payment_status = 'Fully Paid'
            elif total_payments_float > 0:
                order.payment_status = 'Partially Paid'
            else:
                order.payment_status = 'Unpaid'
    
    # Get payment counts
    completed_payments_count = Payment.query.filter_by(payment_status='completed').count()
    failed_payments_count = Payment.query.filter_by(payment_status='failed').count()
    
    return render_template('dashboard.html',
                         pending_orders_count=pending_orders_count,
                         today_orders_count=today_orders_count,
                         pending_payments_count=pending_payments_count,
                         today_revenue=today_revenue,
                         recent_orders=recent_orders,
                         completed_payments_count=completed_payments_count,
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
    
    if status_filter == 'pending':
        orders_query = Order.query.filter_by(approvalstatus=False)
    elif status_filter == 'approved':
        orders_query = Order.query.filter_by(approvalstatus=True)
    else:
        orders_query = Order.query
    
    orders = orders_query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate total amount and payment status for each order
    for order in orders.items:
        total_amount = 0
        if order.order_items:
            for item in order.order_items:
                price = item.final_price or item.original_price or 0
                total_amount += item.quantity * price
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
        db.joinedload(Order.order_items).joinedload(OrderItem.product).joinedload(Product.sub_category).joinedload(SubCategory.category)
    ).get_or_404(order_id)
    
    # Calculate total amount from order items
    total_amount = 0
    if order.order_items:
        for item in order.order_items:
            price = item.final_price or item.original_price or 0
            total_amount += item.quantity * price
    
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
                             total_amount=total_amount,
                             total_payments=total_payments,
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
        if item.productid:
            product = Product.query.get(item.productid)
            if not product:
                missing_products.append(f"Product ID {item.productid}")
                continue
            
            # Warn about low stock but don't block approval
            if product.stock is not None and product.stock < item.quantity:
                low_stock_warnings.append({
                    'name': product.name,
                    'available': product.stock,
                    'requested': item.quantity,
                    'shortage': item.quantity - product.stock
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
            if item.productid:
                product = Product.query.get(item.productid)
                if product:
                    previous_stock = product.stock or 0
                    new_stock = previous_stock - item.quantity
                    
                    # Update product stock (can go negative for backorders)
                    product.stock = new_stock
                    
                    # Create stock transaction record
                    stock_transaction = StockTransaction(
                        productid=item.productid,
                        userid=current_user.id,
                        transaction_type='remove',
                        quantity=item.quantity,
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        notes=f'Stock reduced due to order #{order.id} approval (Backorder: {item.quantity - previous_stock if previous_stock < item.quantity else 0} units)'
                    )
                    db.session.add(stock_transaction)
                else:
                    # Product not found - skip stock transaction (no product to track)
                    pass
            else:
                # Manual item without product ID - skip stock transaction (no product to track)
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
            if item.productid:
                product = Product.query.get(item.productid)
                if product:
                    previous_stock = product.stock or 0
                    new_stock = previous_stock + item.quantity
                    
                    # Update product stock
                    product.stock = new_stock
                    
                    # Create stock transaction record for restoration
                    stock_transaction = StockTransaction(
                        productid=item.productid,
                        userid=current_user.id,
                        transaction_type='add',
                        quantity=item.quantity,
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        notes=f'Stock restored due to order #{order.id} cancellation'
                    )
                    db.session.add(stock_transaction)
                else:
                    # Product not found - skip stock transaction (no product to track)
                    pass
            else:
                # Manual item without product ID - skip stock transaction (no product to track)
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
                    price = item.final_price or item.original_price or 0
                    total_amount += item.quantity * price
            
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
            price = item.final_price or item.original_price or 0
            total_amount += item.quantity * price
    
    # Calculate total payments for this order
    total_payments = db.session.query(func.sum(Payment.amount)).filter(
        Payment.orderid == order.id,
        Payment.payment_status == 'completed'
    ).scalar() or 0
    
    # Calculate remaining amount
    remaining_amount = max(0, total_amount - total_payments)
    
    return render_template('process_payment.html', 
                         order=order, 
                         total_amount=total_amount,
                         total_payments=total_payments,
                         remaining=remaining_amount)

# Payment Management Routes
@app.route('/payments')
@cashier_required
def payments():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'completed':
        payments_query = Payment.query.filter_by(payment_status='completed')
    elif status_filter == 'failed':
        payments_query = Payment.query.filter_by(payment_status='failed')
    else:
        payments_query = Payment.query
    
    payments = payments_query.order_by(Payment.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('payments.html', payments=payments, status_filter=status_filter)

@app.route('/payment/<int:payment_id>')
@cashier_required
def view_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    
    # Calculate total amount for the related order if it exists
    if hasattr(payment, 'order') and payment.order:
        total_amount = 0
        if payment.order.order_items:
            for item in payment.order.order_items:
                price = item.final_price or item.original_price or 0
                total_amount += item.quantity * price
        payment.order.total_amount = total_amount
    
    return render_template('view_payment.html', payment=payment)

@app.route('/payment/<int:payment_id>/process', methods=['POST'])
@cashier_required
def process_payment(payment_id):
    from sqlalchemy import func
    
    payment = Payment.query.get_or_404(payment_id)
    action = request.form.get('action')
    
    if action == 'complete':
        payment.payment_status = 'completed'
        payment.payment_date = datetime.now()
        
        # Check if this completes the order
        if hasattr(payment, 'order') and payment.order:
            total_amount = 0
            if payment.order.order_items:
                for item in payment.order.order_items:
                    price = item.final_price or item.original_price or 0
                    total_amount += item.quantity * price
            
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
    
    # Get sales data
    sales_data = db.session.query(
        func.date(Payment.created_at).label('date'),
        func.count(Payment.id).label('payment_count'),
        func.sum(Payment.amount).label('total_amount')
    ).filter(
        Payment.payment_status == 'completed',
        Payment.created_at >= start_dt,
        Payment.created_at < end_dt
    ).group_by(func.date(Payment.created_at)).order_by(func.date(Payment.created_at)).all()
    
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
        
        # Get all payments for the specific date
        payments = db.session.query(Payment).filter(
            Payment.payment_status == 'completed',
            func.date(Payment.created_at) == date_obj.date()
        ).order_by(Payment.created_at.desc()).all()
        
        # Get order details for each payment
        payment_details = []
        total_revenue = 0
        
        for payment in payments:
            order = Order.query.get(payment.orderid)
            if order:
                # Get order items
                order_items = []
                for item in order.order_items:
                    product_name = item.product.name if item.product else (item.product_name or 'Manual Item')
                    order_items.append({
                        'product_name': product_name,
                        'quantity': item.quantity,
                        'unit_price': float(item.final_price or item.original_price or 0),
                        'total_price': float(item.final_price or item.original_price or 0) * item.quantity
                    })
                
                payment_details.append({
                    'payment': payment,
                    'order': order,
                    'order_items': order_items,
                    'customer_name': f"{order.user.firstname} {order.user.lastname}",
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

# Stock Transactions Route
@app.route('/stock-transactions')
@cashier_required
def stock_transactions():
    page = request.args.get('page', 1, type=int)
    transaction_type = request.args.get('type', 'all')
    product_id = request.args.get('product_id', type=int)
    
    # Build query
    query = StockTransaction.query
    
    if transaction_type != 'all':
        query = query.filter_by(transaction_type=transaction_type)
    
    if product_id:
        query = query.filter_by(productid=product_id)
    
    # Get stock transactions with pagination
    transactions = query.order_by(StockTransaction.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get all products for filter dropdown
    products = Product.query.all()
    
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
    
    # Build query
    query = Product.query
    
    if branch_id:
        query = query.filter_by(branchid=branch_id)
    
    if low_stock:
        query = query.filter(Product.stock < 10)  # Show products with less than 10 in stock
    
    # Add backorder filter option
    backorder = request.args.get('backorder', type=bool)
    if backorder:
        query = query.filter(Product.stock < 0)  # Show products with negative stock (backorders)
    
    # Get products with pagination
    products = query.order_by(Product.name).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get all branches for filter dropdown
    branches = Branch.query.all()
    
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
        quantity = request.form.get('quantity', type=int)
        notes = request.form.get('notes', '')
        
        if not product_id or not adjustment_type or not quantity or quantity <= 0:
            flash('Please fill in all required fields with valid values.', 'error')
            return redirect(url_for('stock_adjustment'))
        
        product = Product.query.get_or_404(product_id)
        
        try:
            previous_stock = product.stock or 0
            
            if adjustment_type == 'add':
                new_stock = previous_stock + quantity
            else:  # remove
                # Allow negative stock for backorders
                new_stock = previous_stock - quantity
            
            # Update product stock
            product.stock = new_stock
            
            # Create stock transaction record
            stock_transaction = StockTransaction(
                productid=product_id,
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
            flash(f'Successfully {action} stock for {product.name}. {stock_status}', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to adjust stock: {str(e)}', 'error')
            print(f"Error adjusting stock: {str(e)}")
    
    # Get all products for the form
    products = Product.query.order_by(Product.name).all()
    
    return render_template('stock_adjustment.html', products=products)
@app.route('/payment/<int:payment_id>/receipt/preview')
@cashier_required
def receipt_preview(payment_id):
    """Show receipt preview page"""
    payment = Payment.query.get_or_404(payment_id)
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

    def format_currency(amount):
        return f"KSh{amount:,.2f}"

    buffer = BytesIO()
    page_width = 210  # safe width for 80mm printer (~74mm printable area)

    doc = BaseDocTemplate(buffer, pagesize=(page_width, 600),
                          leftMargin=10, rightMargin=10, topMargin=10, bottomMargin=10)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template = PageTemplate(id='receipt', frames=[frame])
    doc.addPageTemplates([template])

    story = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=12, alignment=1, spaceAfter=1)   # tighter
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=9, alignment=1, spaceAfter=4)  # reduced
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
            price = item.final_price or item.original_price or 0
            total = item.quantity * price
            # Use product_name from orderdetails if product relationship is null
            product_name = item.product.name if item.product else (item.product_name or "N/A")

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
        total_amount = sum(item.quantity * (item.final_price or item.original_price or 0) for item in order.order_items)
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

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
