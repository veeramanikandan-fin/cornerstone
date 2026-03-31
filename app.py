import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)
DATABASE = 'todo.db'

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
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT 0,
                due_date TEXT,
                priority TEXT,
                category TEXT
            )
        ''')
        db.commit()

@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()

    # Filtering and sorting logic
    category_filter = request.args.get('category')
    sort_by = request.args.get('sort_by', 'id DESC')

    query = 'SELECT * FROM tasks'
    params = []

    if category_filter:
        query += ' WHERE category = ?'
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
    cursor.execute('SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category != ""')
    categories = [row['category'] for row in cursor.fetchall()]

    return render_template('index.html', tasks=tasks, categories=categories, current_category=category_filter, current_sort=sort_by)

@app.route('/add', methods=['POST'])
def add():
    title = request.form.get('title')
    due_date = request.form.get('due_date')
    priority = request.form.get('priority')
    category = request.form.get('category')

    if title:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO tasks (title, due_date, priority, category) VALUES (?, ?, ?, ?)',
            (title, due_date, priority, category)
        )
        db.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['POST'])
def edit(task_id):
    title = request.form.get('title')
    due_date = request.form.get('due_date')
    priority = request.form.get('priority')
    category = request.form.get('category')

    if title:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'UPDATE tasks SET title = ?, due_date = ?, priority = ?, category = ? WHERE id = ?',
            (title, due_date, priority, category, task_id)
        )
        db.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>', methods=['POST'])
def delete(task_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    return redirect(url_for('index'))

@app.route('/toggle/<int:task_id>', methods=['POST'])
def toggle(task_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('UPDATE tasks SET done = NOT done WHERE id = ?', (task_id,))
    db.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
