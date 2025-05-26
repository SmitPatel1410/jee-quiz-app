from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import fitz  # PyMuPDF
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['QUIZ_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static')

db = SQLAlchemy(app)

# User model for authentication
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Updated Question model to include a 'subject'
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=False)
    option4 = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)  # 0 to 3, or -1 if not set
    subject = db.Column(db.String(100), nullable=True) # New column for subject

# SubjectConfig model is no longer used for PDF uploads in this flow,
# but kept here if you still use it for other purposes (e.g., manual question adds).
# If not, you can remove this class and any 'SubjectConfig.query.all()' calls
# where it's no longer relevant.
class SubjectConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_name = db.Column(db.String(100), unique=True, nullable=False)
    start_q_num = db.Column(db.Integer, nullable=False)
    end_q_num = db.Column(db.Integer, nullable=False)


# Create database tables if they don't exist
with app.app_context():
    db.create_all()

@app.route('/')
def home():
    """Redirects the root URL to the login page."""
    return redirect(url_for('login'))

# Helper function to clean text (not strictly needed for answer matching now, but good for consistency)
def clean_text(text):
    """
    Cleans and normalizes text by removing extra whitespace,
    converting to lowercase, and handling specific characters.
    """
    if text is None:
        return ""
    text = text.replace('\xa0', ' ').strip().lower()
    text = re.sub(r'\s+', ' ', text) # Replace multiple spaces with a single space
    text = text.replace('→', ' ').replace('->', ' ') # Handle arrow characters
    return text

def process_pdf_content(text, default_subject='General'):
    """
    Processes the raw text extracted from a PDF to parse questions and their options.
    Assigns the provided default_subject to all questions from this PDF.
    Sets correct_answer to -1, as answers will be manually set by the admin.
    """
    questions_data = []
    try:
        # Split the text by question numbers. This regex looks for a newline, optional spaces,
        # then a number followed by a dot and space (e.g., "\n 1.").
        # It captures the number itself.
        question_chunks = re.split(r'\n\s*(\d+)\.\s', text)

        # Adjust question_chunks to handle preamble if present before the first question.
        parsed_questions = []
        start_index = 0
        if question_chunks and not re.match(r'^\d+$', question_chunks[0].strip()):
            start_index = 1

        for i in range(start_index, len(question_chunks), 2):
            if i + 1 < len(question_chunks):
                try:
                    q_num = int(question_chunks[i].strip())
                    q_content = question_chunks[i+1].strip()
                    parsed_questions.append((q_num, q_content))
                except ValueError:
                    # If conversion to int fails, it's not a valid question number, skip.
                    print(f"Warning: Skipping non-numeric question chunk: '{question_chunks[i]}'")
                    continue

        for q_num, chunk in parsed_questions:
            # All questions from this PDF will get the default_subject
            current_subject = default_subject

            # Find the question text and options.
            # Look for an option prefix (A., B., C., D.) to delineate question text from options.
            first_option_match = re.search(r'^[A-D]\.\s*', chunk, re.MULTILINE)
            question_text = ""
            options_raw_text = ""

            if first_option_match:
                question_text = chunk[:first_option_match.start()].strip()
                options_raw_text = chunk[first_option_match.start():].strip()
            else:
                print(f"Skipping question {q_num}: No options (A, B, C, D) prefixes found.")
                continue

            # Extract options: Use findall to get all 'Letter. Text' pairs.
            # This regex captures the letter and then the text for that option,
            # using a non-greedy match and a lookahead for the next option or end of string.
            option_pairs = re.findall(r'([A-D])\.\s*(.+?)(?=\s*[A-D]\.|\Z)', options_raw_text, re.DOTALL)

            options_dict_raw = {}
            for letter, text_content in option_pairs:
                options_dict_raw[letter] = text_content.strip()

            # Ensure we have exactly 4 options (A, B, C, D). If not, it's a parsing error.
            final_options_dict = {
                'A': options_dict_raw.get('A', ''),
                'B': options_dict_raw.get('B', ''),
                'C': options_dict_raw.get('C', ''),
                'D': options_dict_raw.get('D', '')
            }

            if len([v for v in final_options_dict.values() if v]) != 4:
                print(f"Skipping question {q_num} due to not having exactly 4 valid options parsed.")
                print(f"  Question: {question_text}")
                print(f"  Parsed Options: {final_options_dict}")
                continue

            # Set correct_answer to -1 as per user's request for manual admin selection.
            correct_index = -1

            questions_data.append({
                'question_text': question_text,
                'option1': final_options_dict['A'],
                'option2': final_options_dict['B'],
                'option3': final_options_dict['C'],
                'option4': final_options_dict['D'],
                'correct_answer': correct_index,
                'subject': current_subject # Add the provided subject
            })

    except Exception as e:
        print(f"Critical error during PDF content processing: {e}")
        raise

    return questions_data


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """
    Handles PDF file uploads, extracts questions, and saves them to the database.
    Requires admin login. Assigns a single subject to all questions from the PDF.
    """
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    subject_for_pdf = request.form.get('subject_for_pdf', 'General').strip() # Get subject from form
    if not subject_for_pdf:
        return render_template('admin.html', error="Subject for PDF is required.", questions=Question.query.all(), subject_configs=SubjectConfig.query.all())

    if 'pdf_file' not in request.files:
        return render_template('admin.html', error="No file part", questions=Question.query.all(), subject_configs=SubjectConfig.query.all())

    file = request.files['pdf_file']
    if file.filename == '':
        return render_template('admin.html', error="No selected file", questions=Question.query.all(), subject_configs=SubjectConfig.query.all())

    filepath = os.path.join(app.config['QUIZ_FOLDER'], file.filename)
    file.save(filepath)

    try:
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"

        # Pass the subject provided by the admin for this PDF
        parsed_questions_data = process_pdf_content(text, default_subject=subject_for_pdf)

        for q_data in parsed_questions_data:
            new_q = Question(
                question_text=q_data['question_text'],
                option1=q_data['option1'],
                option2=q_data['option2'],
                option3=q_data['option3'],
                option4=q_data['option4'],
                correct_answer=q_data['correct_answer'],
                subject=q_data['subject'] # This will now be the subject_for_pdf
            )
            db.session.add(new_q)

        db.session.commit()
        return redirect(url_for('admin_panel'))

    except Exception as e:
        # Make sure to remove the uploaded file if processing fails to avoid clutter
        if os.path.exists(filepath):
            os.remove(filepath)
        return render_template('admin.html', error=f"Failed to process PDF: {e}", questions=Question.query.all(), subject_configs=SubjectConfig.query.all())

@app.route('/logout')
def logout():
    """Logs out the current user and redirects to the login page."""
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login and admin login."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        # Admin login (hardcoded for simplicity, consider more robust solutions for production)
        if username == 'admin' and password == 'admin':
            session['username'] = 'admin'
            return redirect(url_for('admin_panel'))

        # Regular user login
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            return redirect(url_for('quiz'))
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@app.route('/quiz')
def quiz():
    """Displays the quiz page for logged-in users."""
    if 'username' not in session or session['username'] == 'admin':
        return redirect(url_for('login'))

    questions = Question.query.all()
    formatted_questions = []
    for q in questions:
        formatted_questions.append({
            'text': q.question_text,
            'options': [q.option1, q.option2, q.option3, q.option4],
            'answer': q.correct_answer, # This will be -1 for newly uploaded questions
            'subject': q.subject # Include subject
        })

    return render_template('quiz.html', username=session['username'], questions=formatted_questions)

@app.route('/api/questions')
def api_questions():
    """Provides quiz questions as a JSON API endpoint."""
    if 'username' not in session or session['username'] == 'admin':
        return jsonify([])

    questions = Question.query.all()
    data = []
    for q in questions:
        data.append({
            'q': q.question_text,
            'options': [q.option1, q.option2, q.option3, q.option4],
            'answer': q.correct_answer,
            'subject': q.subject # Include subject
        })
    return jsonify(data)

@app.route('/results')
def results():
    """Displays the quiz results page."""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('results.html', username=session['username'])

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    """
    Admin panel for managing questions (add, edit, delete).
    Subject configuration management (add/edit/delete SubjectConfig) removed from here
    as per new PDF upload workflow.
    Requires admin login.
    """
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    error = None

    if request.method == 'POST':
        # Handle adding Questions (this part remains as it was)
        # Assuming your add question form has a submit button named 'add_question'
        if 'add_question' in request.form:
            question_text = request.form['question']
            option1 = request.form['option1']
            option2 = request.form['option2']
            option3 = request.form['option3']
            option4 = request.form['option4']
            correct_answer = request.form.get('correct')
            subject = request.form.get('subject', 'General') # Get subject from form, default to 'General'

            if correct_answer not in ['0', '1', '2', '3']:
                correct_answer_int = -1
            else:
                correct_answer_int = int(correct_answer)

            if not all([question_text, option1, option2, option3, option4]):
                error = "All question fields are required."
            else:
                new_q = Question(
                    question_text=question_text,
                    option1=option1,
                    option2=option2,
                    option3=option3,
                    option4=option4,
                    correct_answer=correct_answer_int,
                    subject=subject # Save the subject
                )
                db.session.add(new_q)
                db.session.commit()
                # Redirect to avoid re-submission on refresh
                return redirect(url_for('admin_panel'))
        # If it's a file upload, it will be handled by upload_pdf route which redirects here
        # Any other POST requests will be handled by other routes (e.g., /edit_question, /delete_question)
        # or fall through if not matched.
        else:
            # If a POST request reached here and wasn't handled by 'add_question' or redirected by 'upload_pdf',
            # it might be an unhandled form submission. Re-render with existing data.
            pass


    # GET request: render admin panel
    # subject_configs are still passed to admin.html in case you want to display them
    # or manage them for manually added questions, even if not used by PDF upload directly.
    return render_template('admin.html',
                           questions=Question.query.all(),
                           subject_configs=SubjectConfig.query.all(), # Still pass them
                           error=error)

@app.route('/edit_question/<int:question_id>', methods=['POST'])
def edit_question(question_id):
    """
    Handles editing an existing question.
    Requires admin login.
    """
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    question = Question.query.get_or_404(question_id)
    question.question_text = request.form['question']
    question.option1 = request.form['option1']
    question.option2 = request.form['option2']
    question.option3 = request.form['option3']
    question.option4 = request.form['option4']
    correct_answer = request.form.get('correct')

    if correct_answer not in ['0', '1', '2', '3']:
        question.correct_answer = -1
    else:
        question.correct_answer = int(correct_answer)

    question.subject = request.form.get('subject', 'General') # Update subject from form

    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/delete_question/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    """
    Handles deleting a question.
    Requires admin login.
    """
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    question = Question.query.get(question_id)
    if question:
        db.session.delete(question)
        db.session.commit()
        return redirect(url_for('admin_panel'))
    return "Question not found", 404

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handles new user registration."""
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=50)