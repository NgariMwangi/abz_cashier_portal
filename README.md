# ABZ Cashier Portal

A comprehensive cashier management system for ABZ Hardware with role-based access control, order management, payment processing, and automated receipt generation.

## Features

### 🔐 **Security & Access Control**
- Role-based access control (Cashier only)
- Secure authentication system
- Session management

### 📦 **Order Management**
- Create and manage orders
- Order approval workflow
- Automatic stock reduction on approval
- Stock restoration on order cancellation

### 💳 **Payment Processing**
- Multiple payment methods (Cash, Card, Mobile Money, Bank Transfer)
- Payment status tracking
- Automatic receipt generation

### 🧾 **Receipt Generation**
- **80mm thermal printer compatible** receipts
- Professional PDF format
- Company logo integration
- Complete order and payment details
- Download and print functionality

### 📊 **Inventory Management**
- Real-time stock tracking
- Stock transaction audit trail
- Low stock alerts
- Manual stock adjustments

### 📈 **Reporting & Analytics**
- Sales reports
- Payment analytics
- Stock transaction history

## Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- pip package manager

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd abz-cashier-portal
   ```

2. **Create virtual environment**
   ```bash
   python -m venv env
   
   # On Windows
   env\Scripts\activate
   
   # On macOS/Linux
   source env/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure database**
   - Update `main.py` with your PostgreSQL connection details
   - Ensure database exists and is accessible

5. **Run the application**
   ```bash
   python main.py
   ```

## Receipt Generation

### Features
- **80mm Width**: Optimized for thermal printers
- **Professional Layout**: Clean, organized design
- **Company Branding**: Includes ABZ Hardware logo
- **Complete Information**: Order details, payment info, customer data
- **PDF Format**: High-quality, printable documents

### Usage
1. **From Payment View**: Click "Generate Receipt" button
2. **From Order View**: Click receipt buttons for completed payments
3. **From Payments List**: Click "Receipt" button for completed payments
4. **Download**: Receipts automatically download as PDF files

### Receipt Content
- Company header with logo
- Receipt number and date
- Payment details (amount, method, status)
- Customer information
- Order items with quantities and prices
- Professional footer

## Database Models

### Core Entities
- **Users**: Cashier accounts with role-based access
- **Orders**: Customer orders with approval workflow
- **Products**: Inventory items with stock tracking
- **Payments**: Payment records with receipt generation
- **StockTransactions**: Complete audit trail of stock changes

### Relationships
- Orders → OrderItems → Products
- Products → SubCategories → Categories
- Payments → Orders → Users
- StockTransactions → Products → Users

## Security Features

- **Role Validation**: Only cashier role can access the system
- **Request Validation**: Role checked on every request
- **Session Security**: Secure session management
- **Input Validation**: All user inputs are validated

## API Endpoints

### Authentication
- `POST /login` - User authentication
- `GET /logout` - User logout

### Orders
- `GET /orders` - List all orders
- `GET /order/<id>` - View specific order
- `POST /order/<id>/approve` - Approve order
- `POST /order/<id>/cancel` - Cancel order

### Payments
- `GET /payments` - List all payments
- `GET /payment/<id>` - View specific payment
- `POST /payment/<id>/process` - Process payment
- `GET /payment/<id>/receipt` - Generate receipt

### Stock Management
- `GET /stock-levels` - View current stock levels
- `GET /stock-transactions` - View stock transaction history
- `GET /stock-adjustment` - Manual stock adjustments

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is proprietary software for ABZ Hardware.

## Support

For technical support or questions, please contact the development team.
