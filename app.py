from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from flask import make_response

app = Flask(__name__)
app.secret_key = "supersecretkey123"   # Change this for security

# ----------------------------------
# MySQL Database Configuration
# ----------------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Maneesh1523@localhost/room_expense_tracker'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


# ----------------------------------
# User Loader for Flask-Login
# ----------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ----------------------------------
# Models
# ----------------------------------

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ----------------------------------
# Home Route
# ----------------------------------
@app.route('/')
def home():
    return render_template("home.html")


# ----------------------------------
# Register Route
# ----------------------------------
@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form.get("role", "member")

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        user = User(name=name, email=email, password=hashed_password, role=role)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ----------------------------------
# Login Route
# ----------------------------------
@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


# ----------------------------------
# Logout Route
# ----------------------------------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ----------------------------------
# Dashboard (Protected)
# ----------------------------------
@app.route('/dashboard')
@login_required
def dashboard():

    # ----------------------------
    # ADMIN → sees all expenses
    # MEMBER → sees only their expenses
    # ----------------------------
    if current_user.role == "admin":
        expenses = Expense.query.all()
        users = User.query.all()
    else:
        expenses = Expense.query.filter_by(user_id=current_user.id).all()
        users = [current_user]

    # ----------------------------
    # A. Total Expense
    # ----------------------------
    total_expense = sum(e.amount for e in expenses)

    # ----------------------------
    # B. Money spent by each user
    # ----------------------------
    spent_by_user = {}
    for u in users:
        spent = sum(e.amount for e in expenses if e.user_id == u.id)
        spent_by_user[u.name] = spent

    # ----------------------------
    # C. Equal share (Admin only)
    # ----------------------------
    equal_share = 0
    if current_user.role == "admin" and len(users) > 0:
        equal_share = round(total_expense / len(users), 2)

    # ----------------------------
    # D. Settlement Sheet (Admin only)
    # ----------------------------
    settlement = []
    if current_user.role == "admin":
        for u in users:
            spent = spent_by_user[u.name]
            difference = round(spent - equal_share, 2)

            settlement.append({
                "name": u.name,
                "spent": spent,
                "equal_share": equal_share,
                "difference": difference   # + means gets back, - means owes
            })

    # ----------------------------
    # Render Dashboard
    # ----------------------------
    return render_template(
        "dashboard.html",
        user=current_user,
        total_expense=total_expense,
        spent_by_user=spent_by_user,
        equal_share=equal_share,
        settlement=settlement
    )




# ----------------------------------
# Add Expense (Protected)
# ----------------------------------
@app.route('/add_expense', methods=["GET", "POST"])
@login_required
def add_expense():

    if request.method == "POST":
        amount = float(request.form["amount"])
        category = request.form["category"]
        description = request.form.get("description", "")

        # Convert date properly
        date_str = request.form["date"]
        date = datetime.strptime(date_str, "%Y-%m-%d")

        new_exp = Expense(
            user_id=current_user.id,
            amount=amount,
            category=category,
            date=date,
            description=description
        )

        db.session.add(new_exp)
        db.session.commit()

        flash("Expense added successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_expense.html")



# ----------------------------------
# View Expenses
# ----------------------------------
@app.route('/expenses')
@login_required
def view_expenses():
    if current_user.role == "admin":
        expenses = Expense.query.order_by(Expense.date.desc()).all()
    else:
        expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()

    return render_template("expenses.html", expenses=expenses)

@app.route('/edit-expense/<int:id>', methods=["GET", "POST"])
@login_required
def edit_expense(id):
    exp = Expense.query.get_or_404(id)

    # Only allow owner or admin
    if exp.user_id != current_user.id and current_user.role != "admin":
        flash("Not allowed!", "danger")
        return redirect(url_for("view_expenses"))

    if request.method == "POST":
        exp.amount = float(request.form["amount"])
        exp.category = request.form["category"]
        exp.date = datetime.strptime(request.form["date"], '%Y-%m-%d')
        exp.description = request.form.get("description", "")

        db.session.commit()

        flash("Expense updated!", "success")
        return redirect(url_for("view_expenses"))

    return render_template("edit_expense.html", expense=exp)

@app.route('/delete-expense/<int:id>')
@login_required
def delete_expense(id):
    exp = Expense.query.get_or_404(id)

    if exp.user_id != current_user.id and current_user.role != "admin":
        flash("Not authorized!", "danger")
        return redirect(url_for("view_expenses"))

    db.session.delete(exp)
    db.session.commit()

    flash("Expense deleted!", "info")
    return redirect(url_for("view_expenses"))

# ----------------------------------
# Download PDF Report
# ----------------------------------
@app.route('/download_pdf')
@login_required
def download_pdf():

    # Fetch user-specific expenses
    if current_user.role == "admin":
        expenses = Expense.query.all()
    else:
        expenses = Expense.query.filter_by(user_id=current_user.id).all()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 750, "Room Expense Tracker Report")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 725, f"Generated for: {current_user.name}")
    pdf.drawString(50, 705, f"Total Expenses: ₹{sum(e.amount for e in expenses)}")

    pdf.drawString(50, 680, "----------------------------------------")

    y = 650
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Date")
    pdf.drawString(150, y, "Category")
    pdf.drawString(300, y, "Amount")
    pdf.setFont("Helvetica", 12)

    y -= 20

    # List expenses
    for e in expenses:
        if y < 50:  
            pdf.showPage()
            y = 750

        pdf.drawString(50, y, str(e.date))
        pdf.drawString(150, y, e.category)
        pdf.drawString(300, y, f"₹{e.amount}")
        y -= 20

    pdf.save()
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=expense_report.pdf'

    return response



# ----------------------------------
# Create Tables and Run App
# ----------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    if __name__ == "__main__":
        app.run(debug=True)



