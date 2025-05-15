from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['QUIZ_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static')

db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Question model
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)  # 0, 1, or 2

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        # Check if the user is an admin
        if username == 'admin' and password == 'admin':
            session['username'] = 'admin'
            return redirect(url_for('admin_panel'))

        # Check if the user is a regular user
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            return redirect(url_for('quiz'))
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@app.route('/quiz')
def quiz():
    if 'username' not in session or session['username'] == 'admin':
        return redirect(url_for('login'))

    questions = Question.query.all()
    formatted_questions = []
    for q in questions:
        formatted_questions.append({
            'text': q.question_text,
            'options': [q.option1, q.option2, q.option3],
            'answer': q.correct_answer
        })

    return render_template('quiz.html', username=session['username'], questions=formatted_questions)


@app.route('/api/questions')
def api_questions():
    if 'username' not in session or session['username'] == 'admin':
        return jsonify([])

    questions = Question.query.all()
    data = []
    for q in questions:
        data.append({
            'q': q.question_text,
            'options': [q.option1, q.option2, q.option3],
            'answer': q.correct_answer
        })
    return jsonify(data)

@app.route('/results')
def results():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('results.html', username=session['username'])

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        question_text = request.form['question']
        option1 = request.form['option1']
        option2 = request.form['option2']
        option3 = request.form['option3']
        
        # Get the 'correct' field, ensure it is a valid option
        correct_answer = request.form.get('correct')

        # Check if 'correct' is selected and if it is one of '0', '1', '2'
        if correct_answer not in ['0', '1', '2']:
            return render_template('admin.html', error="Please select a valid correct answer (Option 1, 2, or 3)", questions=Question.query.all())

        # Convert correct_answer to integer
        correct_answer = int(correct_answer)

        # Ensure all fields are filled out
        if not question_text or not option1 or not option2 or not option3:
            return render_template('admin.html', error="All fields must be filled out", questions=Question.query.all())

        # Create and add the new question to the database
        new_q = Question(
            question_text=question_text,
            option1=option1,
            option2=option2,
            option3=option3,
            correct_answer=correct_answer
        )
        db.session.add(new_q)
        db.session.commit()

        return redirect(url_for('admin_panel'))

    # Display all questions
    questions = Question.query.all()
    return render_template('admin.html', questions=questions)


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists')

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/edit_question/<int:question_id>', methods=['POST'])
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    question.question_text = request.form['question']
    question.option1 = request.form['option1']
    question.option2 = request.form['option2']
    question.option3 = request.form['option3']
    question.correct_answer = int(request.form['correct'])

    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/delete_question/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    question = Question.query.get(question_id)
    if question:
        db.session.delete(question)
        db.session.commit()
        return redirect(url_for('admin_panel'))
    return "Question not found", 404


if __name__ == '__main__':
    app.run(debug=True)
