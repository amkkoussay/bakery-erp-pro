# 🥖 Bakery ERP System

A comprehensive Enterprise Resource Planning (ERP) system tailored for bakeries, designed to streamline production, sales, and inventory management with a focus on efficiency and data-driven insights.

## 🌟 Key Features

- **Point of Sale (POS):** Fast and intuitive interface for direct sales processing.
- **Smart Inventory Predictions:** Leverages historical data to forecast raw material needs and prevent stockouts.
- **Production Management:** Track production orders and manage Bill of Materials (BOM).
- **Profitability Reports:** Detailed analysis of production costs vs. sales to calculate profit margins accurately.
- **Supplier & Customer Management:** Integrated records for financial and credit transactions.
- **Online Ordering:** Built-in platform to receive and manage remote customer orders.

## 🏗️ Architecture

The project follows a structured **Flask** architecture using the **Service-Repository Pattern** to ensure maintainability and scalability:

![Architecture Diagram](https://raw.githubusercontent.com/amkkoussay/bakery-erp-pro/main/architecture.png)

### Components:
- **Blueprints (Controllers):** Handle web requests and routing.
- **Services:** Contain the core business logic.
- **Repositories:** Manage direct database interactions using Raw SQL.
- **Database:** SQLite for lightweight and fast operation.

## 📸 Screenshots

| Dashboard | Inventory Predictions | Profitability Reports |
| :---: | :---: | :---: |
| ![Dashboard](https://raw.githubusercontent.com/amkkoussay/bakery-erp-pro/main/dashboard.webp) | ![Predictions](https://raw.githubusercontent.com/amkkoussay/bakery-erp-pro/main/predictions.webp) | ![Profitability](https://raw.githubusercontent.com/amkkoussay/bakery-erp-pro/main/profitability.webp) |

## 🛠️ Technology Stack

- **Backend:** Python (Flask)
- **Database:** SQLite
- **Frontend:** HTML5, CSS3, JavaScript
- **Dependencies:** Werkzeug, Jinja2

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python run.py
   ```

3. **Populate sample data:**
   ```bash
   python sample_data.py
   ```

4. **Default Login:**
   - **Username:** `admin`
   - **Password:** `admin123`

## 📊 Project Structure

```
bakery_erp/
├── app/                 # Main application logic
│   ├── auth/            # Authentication module
│   ├── inventory/       # Inventory management
│   ├── services/        # Business logic (Services)
│   ├── repositories/    # Data access (Repositories)
│   └── templates/       # HTML templates
├── architecture.png     # System architecture diagram
├── bakery_erp.db        # SQLite database
├── run.py               # Application entry point
└── sample_data.py       # Sample data generator
```

## 📈 Roadmap

- [ ] Multi-branch and warehouse support.
- [ ] Integration with online payment gateways.
- [ ] Dedicated mobile app for delivery personnel.
- [ ] Automated WhatsApp/Email notification system.

---
Developed with ❤️ to empower the bakery and confectionery industry.
