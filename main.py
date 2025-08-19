from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Branch, Product, Order, Payment, StockTransaction, Supplier, PurchaseOrder, PurchaseOrderItem, Quotation, QuotationItem
from datetime import datetime
import os
from sqlalchemy import func
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
    
    order = Order.query.get_or_404(order_id)
    
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
    order.approvalstatus = True
    order.approved_at = datetime.now()
    
    try:
        db.session.commit()
        flash(f'Order #{order.id} has been approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to approve order. Please try again.', 'error')
    
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
