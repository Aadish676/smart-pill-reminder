from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3
import os
import pytesseract
from PIL import Image

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DB
def init_db():
    conn = sqlite3.connect('pills.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS pills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            time TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = sqlite3.connect('pills.db')
    c = conn.cursor()
    c.execute("SELECT * FROM pills ORDER BY time")
    pills = c.fetchall()
    conn.close()
    return render_template('index.html', pills=pills)

@app.route('/add', methods=['POST'])
def add_pill():
    name = request.form['pill_name']
    time = request.form['pill_time']
    conn = sqlite3.connect('pills.db')
    c = conn.cursor()
    c.execute("INSERT INTO pills (name, time) VALUES (?, ?)", (name, time))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/ocr', methods=['POST'])
def ocr_extract():
    if 'prescription' not in request.files:
        return "No file", 400

    file = request.files['prescription']
    if file.filename == '':
        return "Empty filename", 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    text = pytesseract.image_to_string(Image.open(filepath))
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return render_template("index.html", pills=get_pills(), ocr_lines=lines)

def get_pills():
    conn = sqlite3.connect('pills.db')
    c = conn.cursor()
    c.execute("SELECT * FROM pills ORDER BY time")
    pills = c.fetchall()
    conn.close()
    return pills

