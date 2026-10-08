from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import mysql.connector
import os

app = Flask(__name__)
app.secret_key = "change-me-to-a-long-random-string"

# ---------- Нейросеть (можно отключить, обернув в try) ----------
llm = None
try:
    from llama_cpp import Llama
    llm = Llama(
        model_path="./models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        n_ctx=4096,
        n_threads=os.cpu_count() or 4,
        n_gpu_layers=0,
        verbose=False,
    )
    print("Модель загружена")
except Exception as e:
    print("Нейросеть не загружена:", e)


# ---------- БД ----------
def get_db():
    return mysql.connector.connect(
        host="185.114.247.43",
        port=3306,
        database="sch688_vvedenie",
        user="sch688_vvedenie",
        password="Qwerty123",
        charset="utf8mb4",
        use_unicode=True,
    )


# ---------- Декоратор ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# ---------- Регистрация ----------
@app.route('/user_register', methods=['POST'])
def user_register():
    req = request.get_json() or {}
    name = (req.get('name') or '').strip()
    surname = (req.get('surname') or '').strip()
    email = (req.get('email') or '').strip()
    password = req.get('password') or ''

    if not name or not email or not password:
        return jsonify({'result': False, 'error': 'Заполните имя, email и пароль'})

    password_hash = generate_password_hash(password)   # сохраняем ЦЕЛИКОМ

    cnx = get_db()
    cur = cnx.cursor()
    try:
        cur.execute(
            'INSERT INTO `users`(`username`, `surname`, `email`, `password_hash`) '
            'VALUES (%s, %s, %s, %s)',
            (name, surname, email, password_hash)
        )
        cnx.commit()
    except mysql.connector.IntegrityError:
        cur.close(); cnx.close()
        return jsonify({'result': False, 'error': 'Такой email уже зарегистрирован'})
    except Exception as e:
        cur.close(); cnx.close()
        return jsonify({'result': False, 'error': str(e)})

    cur.close(); cnx.close()
    return jsonify({'result': True})


# ---------- Логин ----------
@app.route('/user_login', methods=['POST'])
def user_login():
    req = request.get_json() or {}
    email = (req.get('email') or '').strip()
    password = req.get('password') or ''

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute('SELECT * FROM `users` WHERE `email` = %s', (email,))
    user = cur.fetchone()
    cur.close(); cnx.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'result': False, 'error': 'Неверный email или пароль'})

    session['user_id'] = user['id']
    return jsonify({'result': True})


# ---------- Выход ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------- ЛК ----------
@app.route('/lk')
@login_required
def lk():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        'SELECT `username`, `surname`, `email`, `balance` '
        'FROM `users` WHERE `id` = %s',
        (session['user_id'],)
    )
    user = cur.fetchone()
    cur.close(); cnx.close()
    return render_template('lk.html', user=user)


# ---------- История ----------
@app.route('/history')
@login_required
def history():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        'SELECT `message`, `answer`, `created_at` FROM `requests` '
        'WHERE `user_id` = %s ORDER BY `created_at` DESC LIMIT 100',
        (session['user_id'],)
    )
    rows = cur.fetchall()
    cur.close(); cnx.close()
    return render_template('history.html', rows=rows)


# ---------- Чат ----------
@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html')


@app.route('/chat_send', methods=['POST'])
@login_required
def chat_send():
    if llm is None:
        return jsonify({'error': 'Нейросеть не загружена'}), 503

    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Пустой запрос'}), 400

    try:
        out = llm.create_chat_completion(
            messages=[
                {'role': 'system',
                 'content': 'Ты — вежливый помощник школьного портала. Отвечай кратко на русском.'},
                {'role': 'user', 'content': message},
            ],
            max_tokens=400,
            temperature=0.7,
        )
        answer = out['choices'][0]['message']['content']
    except Exception as e:
        return jsonify({'error': f'Ошибка модели: {e}'}), 500

    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        'INSERT INTO `requests` (`user_id`, `message`, `answer`) VALUES (%s, %s, %s)',
        (session['user_id'], message, answer)
    )
    cnx.commit()
    cur.close(); cnx.close()

    return jsonify({'answer': answer})


# ---------- Страницы ----------
@app.route("/", methods=['GET', 'POST'])
def registration():
    return render_template('registration.html')


@app.route("/login", methods=['GET', 'POST'])
def login():
    return render_template('login.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)