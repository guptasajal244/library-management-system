import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy.exc import IntegrityError, OperationalError
from datetime import datetime, timedelta
from sqlalchemy import or_

app = Flask(__name__)
# Fix C-3: Read SECRET_KEY from environment; fall back only for local dev.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'library_management_system_dev_only')
# Fix C-1: Read DB credentials from environment; fall back only for local dev.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'mysql+pymysql://root:root@localhost/library'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Fix C-2: Recycle idle connections before MySQL's wait_timeout; pre-ping
# validates each connection before checkout, preventing "server has gone away".
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True,
    'pool_size': 5,
    'max_overflow': 10,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # redirect unauthenticated users to /login

# Database models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    issued_books = db.Column(db.Integer, default=0)

class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def get_id(self):
        # Prefix with "a" so load_user() can distinguish Admin sessions from User sessions.
        return f'a{self.id}'

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(50), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    genre = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

class IssuedBooks(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    # Fix Q-3: Schema uses TIMESTAMP; DateTime matches the actual column type.
    issued_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    return_date = db.Column(db.Date, nullable=False)

class Orders(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userId = db.Column(db.Integer, nullable=False)
    BookName = db.Column(db.String(200), nullable=False)
    Author = db.Column(db.String(200), nullable=False)
    orderDate = db.Column(db.Date, default=datetime.utcnow, nullable=False)
 
# Configure your user loader
# Admin sessions carry an "a" prefix (e.g. "a1") set by Admin.get_id().
@login_manager.user_loader
def load_user(user_id):
    # Fix R-5: Catch OperationalError when MySQL is unreachable; return None
    # so Flask-Login treats the session as anonymous instead of raising a 500.
    # Fix Q-1: db.session.get() replaces the SQLAlchemy-2.0-removed Query.get().
    try:
        if str(user_id).startswith('a'):
            return db.session.get(Admin, int(str(user_id)[1:]))
        return db.session.get(User, int(user_id))
    except OperationalError:
        return None


# ---------------------------------------------------------------------------
# Role-based decorator: restricts a route to authenticated Admin users only.
# ---------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not isinstance(current_user, Admin):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Fix R-1, R-2: Restrict issue/return routes to authenticated User sessions.
# An Admin session has no `issued_books` field; accessing it causes AttributeError.
def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not isinstance(current_user, User):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
    
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('loginType')

        if login_type == 'admin':
            return redirect(url_for('admin_login'))
        elif login_type == 'user':
            return redirect(url_for('user_login'))

    return render_template('index.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    invalid_credentials = False
    if request.method == 'POST':
        admin_username = request.form.get('adminUsername')
        admin_password = request.form.get('adminPassword')

        # Fetch by username only, then verify password hash (never compare plain text).
        admin = Admin.query.filter_by(username=admin_username).first()

        if admin and check_password_hash(admin.password, admin_password):
            login_user(admin, remember=False)
            return redirect(url_for('admin_dashboard'))
        else:
            invalid_credentials = True

    # Fix R-6: Return 401 when credentials were submitted but failed.
    status = 401 if invalid_credentials else 200
    return render_template('admin_login.html', invalid_credentials=invalid_credentials), status

@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    invalid_credentials = False

    if request.method == 'POST':
        user_username = request.form.get('userUsername')
        user_password = request.form.get('userPassword')

        # Fetch by username only, then verify password hash (never compare plain text).
        user = User.query.filter_by(username=user_username).first()

        if user and check_password_hash(user.password, user_password):
            login_user(user, remember=False)
            return redirect(url_for('user_dashboard'))
        else:
            invalid_credentials = True

    # Fix R-6: Return 401 when credentials were submitted but failed.
    status = 401 if invalid_credentials else 200
    return render_template('user_login.html', invalid_credentials=invalid_credentials), status

@app.route('/logout')
def logout():
    logout_user()  # clears the server-side session; BUG-06 fix
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/user_dashboard')
@login_required  # guarantees current_user is a real User when the template renders
def user_dashboard():
    return render_template('user_dashboard.html')


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    success_message = None

    if request.method == 'POST':
        # Get user details from the form (ID is auto-incremented — never trust client-supplied PK)
        name = request.form.get('newUserName')
        username = request.form.get('newUserUsername')
        password = request.form.get('newUserPassword')

        # Hash the password before storing — never persist plain text
        hashed_pw = generate_password_hash(password)
        new_user = User(name=name, username=username, password=hashed_pw)
        db.session.add(new_user)
        try:
            db.session.commit()
            success_message = 'User added successfully!'
        except IntegrityError:
            db.session.rollback()
            success_message = 'Error: Username already exists. Please choose a different username.'

    return render_template('add_user.html', success_message=success_message)

@app.route('/add_book', methods=['GET', 'POST'])
@login_required
@admin_required
def add_book():
    success_message = None

    if request.method == 'POST':
        # Get book details from the form
        isbn = request.form.get('bookISBN')
        title = request.form.get('bookTitle')
        author = request.form.get('bookAuthor')
        genre = request.form.get('bookGenre')
        quantity = request.form.get('bookQuantity')

        # Backend validation: quantity must be a positive integer
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            success_message = 'Error: Quantity must be a positive whole number.'
            return render_template('add_book.html', success_message=success_message)

        # Check if ISBN is unique before adding the book
        if Book.query.filter_by(isbn=isbn).first() is not None:
            success_message = 'Book with the provided ISBN already exists. Please use a unique ISBN.'
        else:
            # Create a new book object and add it to the database
            new_book = Book(isbn=isbn, title=title, author=author, genre=genre, quantity=quantity)
            db.session.add(new_book)
            # Fix T-3: The pre-check above is a TOCTOU race; a concurrent insert
            # of the same ISBN will raise IntegrityError here — handle it explicitly.
            try:
                db.session.commit()
                success_message = 'Book added successfully!'
            except IntegrityError:
                db.session.rollback()
                success_message = 'Error: A book with this ISBN already exists.'

    return render_template('add_book.html', success_message=success_message)

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    books = Book.query.all()
    return render_template('search.html',books = books)

@app.route('/issue_book/<isbn>', methods=['POST'])
@login_required
@user_required  # Fix R-1: Block Admin sessions; Admin has no issued_books field.
def issue_book(isbn):

    # Fix R-4: with_for_update() acquires a row-level lock, preventing two
    # concurrent requests from both reading quantity > 0 and both decrementing it.
    book = Book.query.filter_by(isbn=isbn).with_for_update().first()

    # Check if the user has already issued a copy of the same book
    existing_issue = IssuedBooks.query.filter_by(user_id=current_user.id, isbn=isbn).first()

    # Check if the user has already issued the maximum allowed books (6)
    if current_user.issued_books >= 6:
        return jsonify({'success': False, 'message': 'You have reached the maximum limit of issued books (6).'})

    # Check if the book is available and the user has not already issued a copy of it
    if book and (book.quantity > 0) and not existing_issue:
        # Calculate return date as 7 days from the issued date
        issued_date = datetime.utcnow()
        return_date = issued_date + timedelta(days=7)

        # Update the IssuedBooks table
        issued_book = IssuedBooks(
            isbn=book.isbn,
            title=book.title,
            user_id=current_user.id,
            issued_date=issued_date,
            return_date=return_date
        )
        db.session.add(issued_book)

        # Update the User table's issued_books field
        current_user.issued_books += 1

        # Decrement the book quantity and save to the database
        book.quantity -= 1

        # Fix T-1: Commit all changes; roll back explicitly on any DB error so the
        # session stays clean and in-memory state does not drift from the database.
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Database error. Please try again.'})

        return jsonify({'success': True, 'message': 'Book issued successfully!'})
    elif existing_issue:
        db.session.rollback()  # Release the row-level lock immediately
        return jsonify({'success': False, 'message': 'You have already issued a copy of this book.'})
    else:
        db.session.rollback()  # Release the row-level lock immediately
        return jsonify({'success': False, 'message': 'Failed to issue the book. Insufficient quantity.'})

@app.route('/issued_books')
@login_required
@admin_required
def issued_books():
    issued_books = IssuedBooks.query.all()
    return render_template('issued_books.html', issued_books = issued_books)

@app.route('/return_book')
@login_required
@user_required  # Fix R-2: Block Admin sessions; Admin has no issued_books field.
def return_book():
    # Get the books issued by the current user
    issued_books = IssuedBooks.query.filter_by(user_id=current_user.id).all()

    return render_template('return_book.html', issued_books=issued_books)

@app.route('/return_book/<isbn>', methods=['POST'])
@login_required
@user_required  # Fix R-2: Block Admin sessions.
def handle_return_book(isbn):
    book = Book.query.filter_by(isbn=isbn).first()

    # Check if the book is issued to the current user and not returned yet
    issued_book = IssuedBooks.query.filter_by(user_id=current_user.id, isbn=isbn).first()

    if book and issued_book:
        db.session.delete(issued_book)

        # Fix R-3: Guard against the counter going below zero due to data drift.
        current_user.issued_books = max(0, current_user.issued_books - 1)

        # Increment the book quantity and save to the database
        book.quantity += 1

        # Fix T-2: Explicit rollback on commit failure keeps the session clean.
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Database error. Please try again.'})

        return jsonify({'success': True, 'message': 'Book returned successfully!'})
    else:
        return jsonify({'success': False, 'message': 'Failed to return the book. Book not found or already returned.'})


@app.route('/view_all_books')
@login_required
@admin_required
def view_all_books():
    books = Book.query.all()
    return render_template('view_all_books.html', books=books)

@app.route('/place_order', methods=['GET', 'POST'])
@login_required
def place_order():
    if request.method == 'POST':
        author_name = request.form.get('authorName')
        book_title = request.form.get('bookTitle')

        # Check if the user has already placed a similar order
        existing_order = Orders.query.filter_by(userId=current_user.id, Author=author_name, BookName=book_title).first()

        if existing_order:
            error_message = 'You have already placed an order for this book and author.'
            return render_template('place_order.html', message=error_message)

        # If no similar order found, proceed with placing the order
        new_order = Orders(userId=current_user.id, Author=author_name, BookName=book_title)
        db.session.add(new_order)
        # Fix T-4: Guard the commit so any DB error returns a user-facing message.
        try:
            db.session.commit()
            success_message = 'Order placed successfully!'
        except Exception:
            db.session.rollback()
            success_message = 'Failed to place order. Please try again.'
        return render_template('place_order.html', message=success_message)

    return render_template('place_order.html')

@app.route('/view_orders')
@login_required
@admin_required
def view_orders():
    # Fetch all orders from the database
    orders = Orders.query.all()
    return render_template('view_orders.html', orders=orders)

if __name__ == '__main__':
    # Fix C-4: Probe the DB at startup so a missing MySQL instance produces a
    # clear warning rather than a silent 500 on the first DB-touching request.
    try:
        with app.app_context():
            db.session.execute(db.text('SELECT 1'))
    except Exception as e:
        print(f"[WARNING] Cannot connect to MySQL at startup: {e}")
        print("[WARNING] The app will start, but all database routes will fail until MySQL is reachable.")
    app.run(debug=True)
