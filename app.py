import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-in-production'
app.config['MAIL_SERVER'] = 'localhost'
app.config['MAIL_PORT'] = 8025
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = None
app.config['MAIL_PASSWORD'] = None
app.config['MAIL_DEFAULT_SENDER'] = 'noreply@acme.inc'

mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE = 'todo.db'
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

class User(UserMixin):
    def __init__(self, id, email, password_hash, is_verified=False):
        self.id = id
        self.email = email
        self.password_hash = password_hash
        self.is_verified = is_verified

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        return User(id=user['id'], email=user['email'], password_hash=user['password_hash'], is_verified=user['is_verified'])
    return None

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN NOT NULL DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT 0,
                due_date TEXT,
                priority TEXT,
                category TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                completed_today BOOLEAN NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        db.commit()

def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Error sending email (Is a local SMTP server running?): {e}")
        print(f"--- EMAIL CONTENT TO {recipient} ---")
        print(body)
        print("-----------------------------------")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            flash('Email already registered.', 'error')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        cursor.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', (email, hashed_password))
        db.commit()

        token = serializer.dumps(email, salt='email-confirm')
        verification_link = url_for('verify_email', token=token, _external=True)
        send_email('Verify Your Account', email, f'Click here to verify: {verification_link}')

        flash('Registration successful! Please check your email to verify your account.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/verify/<token>')
def verify_email(token):
    try:
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
    except:
        flash('The confirmation link is invalid or has expired.', 'error')
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute('UPDATE users SET is_verified = 1 WHERE email = ?', (email,))
    db.commit()
    flash('Your account has been verified! You can now log in.', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user_data = cursor.fetchone()

        if not user_data or not check_password_hash(user_data['password_hash'], password):
            flash('Please check your login details and try again.', 'error')
            return redirect(url_for('login'))

        if not user_data['is_verified']:
            flash('Please verify your email address before logging in.', 'error')
            return redirect(url_for('login'))

        user = User(id=user_data['id'], email=user_data['email'], password_hash=user_data['password_hash'], is_verified=user_data['is_verified'])
        login_user(user)
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            token = serializer.dumps(email, salt='password-reset')
            reset_link = url_for('reset_password', token=token, _external=True)
            send_email('Password Reset Request', email, f'Click here to reset your password: {reset_link}')
        flash('If an account exists with that email, a password reset link has been sent.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except:
        flash('The reset link is invalid or has expired.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = generate_password_hash(password)
        db = get_db()
        cursor = db.cursor()
        cursor.execute('UPDATE users SET password_hash = ? WHERE email = ?', (hashed_password, email))
        db.commit()
        flash('Your password has been updated! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/')
@login_required
def index():
    db = get_db()
    cursor = db.cursor()

    # Filtering and sorting logic
    category_filter = request.args.get('category')
    sort_by = request.args.get('sort_by', 'id DESC')

    query = 'SELECT * FROM tasks WHERE user_id = ?'
    params = [current_user.id]

    if category_filter:
        query += ' AND category = ?'
        params.append(category_filter)

    if sort_by == 'due_date':
        query += ' ORDER BY due_date ASC'
    elif sort_by == 'priority':
        query += ' ORDER BY CASE priority WHEN "High" THEN 1 WHEN "Medium" THEN 2 WHEN "Low" THEN 3 ELSE 4 END ASC'
    else:
        query += ' ORDER BY id DESC'

    cursor.execute(query, params)
    tasks = cursor.fetchall()

    # Get unique categories for the filter dropdown
    cursor.execute('SELECT DISTINCT category FROM tasks WHERE user_id = ? AND category IS NOT NULL AND category != ""', (current_user.id,))
    categories = [row['category'] for row in cursor.fetchall()]

    return render_template('index.html', tasks=tasks, categories=categories, current_category=category_filter, current_sort=sort_by)

@app.route('/add', methods=['POST'])
@login_required
def add():
    title = request.form.get('title')
    due_date = request.form.get('due_date')
    priority = request.form.get('priority')
    category = request.form.get('category')

    if title:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO tasks (user_id, title, due_date, priority, category) VALUES (?, ?, ?, ?, ?)',
            (current_user.id, title, due_date, priority, category)
        )
        db.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['POST'])
@login_required
def edit(task_id):
    title = request.form.get('title')
    due_date = request.form.get('due_date')
    priority = request.form.get('priority')
    category = request.form.get('category')

    if title:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'UPDATE tasks SET title = ?, due_date = ?, priority = ?, category = ? WHERE id = ? AND user_id = ?',
            (title, due_date, priority, category, task_id, current_user.id)
        )
        db.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>', methods=['POST'])
@login_required
def delete(task_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, current_user.id))
    db.commit()
    return redirect(url_for('index'))

@app.route('/toggle/<int:task_id>', methods=['POST'])
@login_required
def toggle(task_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('UPDATE tasks SET done = NOT done WHERE id = ? AND user_id = ?', (task_id, current_user.id))
    db.commit()
    return redirect(url_for('index'))

@app.route('/pomodoro')
@login_required
def pomodoro():
    return render_template('pomodoro.html')

@app.route('/habits')
@login_required
def habits():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM habits WHERE user_id = ? ORDER BY id DESC', (current_user.id,))
    habits_list = cursor.fetchall()
    return render_template('habits.html', habits=habits_list)

@app.route('/add_habit', methods=['POST'])
@login_required
def add_habit():
    name = request.form.get('name')
    if name:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('INSERT INTO habits (user_id, name) VALUES (?, ?)', (current_user.id, name))
        db.commit()
    return redirect(url_for('habits'))

@app.route('/toggle_habit/<int:habit_id>', methods=['POST'])
@login_required
def toggle_habit(habit_id):
    db = get_db()
    cursor = db.cursor()
    # Logic to handle toggle and streak update
    cursor.execute('SELECT completed_today, streak FROM habits WHERE id = ? AND user_id = ?', (habit_id, current_user.id))
    habit = cursor.fetchone()

    if habit:
        is_completed = habit['completed_today']
        current_streak = habit['streak']

        if is_completed:
            # If it was completed, uncomplete it and decrease streak
            new_streak = max(0, current_streak - 1)
            cursor.execute('UPDATE habits SET completed_today = 0, streak = ? WHERE id = ?', (new_streak, habit_id))
        else:
            # If not completed, mark as completed and increase streak
            new_streak = current_streak + 1
            cursor.execute('UPDATE habits SET completed_today = 1, streak = ? WHERE id = ?', (new_streak, habit_id))

        db.commit()

    return redirect(url_for('habits'))

@app.route('/delete_habit/<int:habit_id>', methods=['POST'])
@login_required
def delete_habit(habit_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM habits WHERE id = ? AND user_id = ?', (habit_id, current_user.id))
    db.commit()
    return redirect(url_for('habits'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
