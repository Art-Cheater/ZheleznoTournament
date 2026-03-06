from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_caching import Cache
import sqlite3
from database import init_db
import json
from functools import wraps
import os
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'zhelezno_dev_key_2024')

# Настройки сессии
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = False  # Для разработки
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Настройка кеширования
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 минут
cache = Cache(app)

DB_NAME = "event.db"
CACHE_TIMEOUT = 10  # Кешируем на 10 секунд для главной страницы

# Конфигурация администратора
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "zhelezno2024"

def login_required(f):
    """Декоратор для защиты админ-маршрутов"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash("Необходима авторизация администратора", "error")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def station_operator_required(f):
    """Декоратор для защиты маршрутов операторов станций"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('operator_logged_in'):
            flash("Необходима авторизация оператора", "error")
            return redirect(url_for('operator_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    """Получение соединения с БД с увеличенным таймаутом"""
    return sqlite3.connect(DB_NAME, timeout=30)

def invalidate_cache():
    """Сбрасывает кеш при изменениях"""
    cache.delete('all_teams_scores')
    cache.delete('api_stations')
    print("🗑️ Кеш сброшен")

@cache.cached(timeout=CACHE_TIMEOUT, key_prefix='all_teams_scores')
def get_cached_team_scores():
    """Кешированная версия для всех станций"""
    return get_team_scores()

def get_team_scores(station_id=None):
    """Получить сумму баллов для каждой команды"""
    conn = get_db()
    cursor = conn.cursor()
    
    if station_id:
        # Только для конкретной станции
        query = """
            SELECT teams.id, teams.name, COALESCE(SUM(scores.points), 0) as total_points
            FROM teams
            LEFT JOIN scores ON teams.id = scores.team_id AND scores.station_id = ?
            GROUP BY teams.id
            ORDER BY total_points DESC
        """
        cursor.execute(query, (station_id,))
    else:
        # Все станции
        query = """
            SELECT teams.id, teams.name, COALESCE(SUM(scores.points), 0) as total_points
            FROM teams
            LEFT JOIN scores ON teams.id = scores.team_id
            GROUP BY teams.id
            ORDER BY total_points DESC
        """
        cursor.execute(query)
    
    teams = cursor.fetchall()
    conn.close()
    return [{"id": t[0], "name": t[1], "points": t[2]} for t in teams]

@app.route("/")
def index():
    """Главная страница с рейтингом (доступна всем)"""
    return render_template("index.html")

@app.route("/api/stations")
@cache.cached(timeout=60)  # Станции меняются редко, кешируем на минуту
def api_stations():
    """API для получения списка станций"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM stations ORDER BY name")
    stations = cursor.fetchall()
    conn.close()
    return jsonify([{"id": s[0], "name": s[1]} for s in stations])

@app.route("/api/scores")
def api_scores():
    """API для получения актуальных баллов"""
    station_id = request.args.get('station')
    
    # Для всех станций используем кеш
    if not station_id or station_id == 'all':
        teams = get_cached_team_scores()
    else:
        # Для конкретной станции не кешируем
        teams = get_team_scores(int(station_id))
    
    return jsonify(teams)

# ========== АВТОРИЗАЦИЯ АДМИНА ==========

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Страница входа в админку"""
    # Если уже авторизован как админ, перенаправляем в админку
    if session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            # Очищаем старую сессию и создаем новую
            session.clear()
            session['admin_logged_in'] = True
            session.permanent = False
            flash("Успешный вход!", "success")
            return redirect(url_for('admin'))
        else:
            flash("Неверное имя пользователя или пароль", "error")
    
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    """Выход из админки"""
    session.pop('admin_logged_in', None)
    flash("Вы вышли из системы", "info")
    return redirect(url_for('admin_login'))

# ========== АВТОРИЗАЦИЯ ОПЕРАТОРА СТАНЦИИ ==========

@app.route("/operator/login", methods=["GET", "POST"])
def operator_login():
    """Страница входа для операторов станций"""
    # Если уже авторизован как оператор, перенаправляем в панель
    if session.get('operator_logged_in'):
        return redirect(url_for('operator_panel'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, station_id FROM station_operators 
            WHERE username = ? AND password = ?
        """, (username, password))
        
        operator = cursor.fetchone()
        conn.close()
        
        if operator:
            # Очищаем старую сессию и создаем новую
            session.clear()
            session['operator_logged_in'] = True
            session['operator_id'] = operator[0]
            session['operator_station_id'] = operator[1]
            session.permanent = False
            flash("Успешный вход!", "success")
            return redirect(url_for('operator_panel'))
        else:
            flash("Неверное имя пользователя или пароль", "error")
    
    return render_template("operator_login.html")

@app.route("/operator/logout")
def operator_logout():
    """Выход из панели оператора"""
    session.pop('operator_logged_in', None)
    session.pop('operator_id', None)
    session.pop('operator_station_id', None)
    flash("Вы вышли из системы", "info")
    return redirect(url_for('operator_login'))

# ========== ЗАЩИЩЕННЫЕ АДМИН-МАРШРУТЫ ==========

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    """Панель администратора (только для авторизованных)"""
    conn = get_db()
    cursor = conn.cursor()

    # Добавление команды
    if request.method == "POST" and request.form.get("team_name"):
        team_name = request.form.get("team_name")
        if team_name:
            cursor.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", (team_name,))
            conn.commit()
            flash(f"Команда {team_name} добавлена", "success")
            invalidate_cache()  # Сбрасываем кеш

    # Получаем команды
    cursor.execute("SELECT id, name FROM teams ORDER BY name")
    teams = cursor.fetchall()

    # Получаем станции
    cursor.execute("SELECT id, name FROM stations ORDER BY name")
    stations = cursor.fetchall()

    # Получаем операторов станций
    cursor.execute("""
        SELECT so.id, so.username, s.name as station_name
        FROM station_operators so
        JOIN stations s ON s.id = so.station_id
        ORDER BY s.name, so.username
    """)
    operators = cursor.fetchall()

    # Получаем баллы с team_id и station_id
    cursor.execute("""
        SELECT scores.id, teams.name, stations.name, scores.points, 
               teams.id as team_id, stations.id as station_id
        FROM scores
        JOIN teams ON teams.id = scores.team_id
        JOIN stations ON stations.id = scores.station_id
        ORDER BY teams.name, stations.name
    """)
    scores = cursor.fetchall()
    
    # Получаем сумму баллов для каждой команды
    team_totals = get_team_scores()

    conn.close()

    return render_template(
        "admin.html",
        teams=teams,
        stations=stations,
        operators=operators,
        scores=scores,
        team_totals=team_totals
    )

@app.route("/add_station", methods=["POST"])
@login_required
def add_station():
    station_name = request.form.get("station_name")
    if station_name:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO stations (name) VALUES (?)", (station_name,))
        conn.commit()
        conn.close()
        invalidate_cache()  # Сбрасываем кеш
        flash(f"Станция {station_name} добавлена", "success")
    return redirect(url_for("admin"))

@app.route("/add_operator", methods=["POST"])
@login_required
def add_operator():
    username = request.form.get("username")
    password = request.form.get("password")
    station_id = request.form.get("station_id")
    
    if username and password and station_id:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO station_operators (username, password, station_id)
                VALUES (?, ?, ?)
            """, (username, password, station_id))
            conn.commit()
            flash(f"Оператор {username} успешно добавлен", "success")
        except sqlite3.IntegrityError:
            flash("Оператор с таким именем уже существует", "error")
        finally:
            conn.close()
    return redirect(url_for("admin"))

@app.route("/delete_operator/<int:operator_id>", methods=["POST"])
@login_required
def delete_operator(operator_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM station_operators WHERE id = ?", (operator_id,))
    conn.commit()
    conn.close()
    flash("Оператор удален", "success")
    return redirect(url_for("admin"))

@app.route("/delete_team/<int:team_id>", methods=["POST"])
@login_required
def delete_team(team_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scores WHERE team_id = ?", (team_id,))
    cursor.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Команда удалена", "success")
    return redirect(url_for("admin"))

@app.route("/delete_station/<int:station_id>", methods=["POST"])
@login_required
def delete_station(station_id):
    conn = get_db()
    cursor = conn.cursor()
    # Сначала удаляем операторов этой станции
    cursor.execute("DELETE FROM station_operators WHERE station_id = ?", (station_id,))
    cursor.execute("DELETE FROM scores WHERE station_id = ?", (station_id,))
    cursor.execute("DELETE FROM stations WHERE id = ?", (station_id,))
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Станция удалена", "success")
    return redirect(url_for("admin"))

@app.route("/admin/save_score", methods=["POST"])
@login_required
def admin_save_score():
    """Сохранение баллов администратором"""
    team_id = request.form.get("team_id")
    station_id = request.form.get("station_id")
    points = request.form.get("points")

    if not team_id or not station_id or not points:
        flash("Ошибка: не выбрана команда или станция", "error")
        return redirect(url_for("admin"))

    try:
        points = int(points)
        team_id = int(team_id)
        station_id = int(station_id)
    except ValueError:
        flash("Ошибка: некорректные данные", "error")
        return redirect(url_for("admin"))

    if points <= 0:
        flash("Количество баллов должно быть положительным числом", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    cursor = conn.cursor()

    # Проверяем, есть ли уже запись
    cursor.execute("""
        SELECT points FROM scores 
        WHERE team_id = ? AND station_id = ?
    """, (team_id, station_id))
    
    existing = cursor.fetchone()
    
    if existing:
        # Если запись есть - добавляем баллы к существующим
        new_points = existing[0] + points
        cursor.execute("""
            UPDATE scores 
            SET points = ? 
            WHERE team_id = ? AND station_id = ?
        """, (new_points, team_id, station_id))
        flash(f"Добавлено {points} баллов к существующим. Текущий результат: {new_points}", "success")
    else:
        # Если записи нет - создаем новую
        cursor.execute("""
            INSERT INTO scores (team_id, station_id, points)
            VALUES (?, ?, ?)
        """, (team_id, station_id, points))
        flash(f"Добавлено {points} баллов", "success")

    conn.commit()
    conn.close()
    
    # Сбрасываем кеш после изменений
    invalidate_cache()
    
    return redirect(url_for("admin"))

@app.route("/admin/subtract_score", methods=["POST"])
@login_required
def admin_subtract_score():
    """Вычитание баллов администратором (в случае ошибки)"""
    team_id = request.form.get("team_id")
    station_id = request.form.get("station_id")
    points = request.form.get("points")
    
    # Отладка
    print(f"DEBUG: team_id={team_id}, station_id={station_id}, points={points}")

    if not team_id or not station_id or not points:
        flash("Ошибка: не выбрана команда или станция", "error")
        return redirect(url_for("admin"))

    try:
        points = int(points)
        team_id = int(team_id)
        station_id = int(station_id)
    except ValueError:
        flash("Ошибка: некорректные данные", "error")
        return redirect(url_for("admin"))

    if points <= 0:
        flash("Количество баллов должно быть положительным числом", "error")
        return redirect(url_for("admin"))

    conn = get_db()
    cursor = conn.cursor()

    # Проверяем, есть ли запись
    cursor.execute("""
        SELECT id, points FROM scores 
        WHERE team_id = ? AND station_id = ?
    """, (team_id, station_id))
    
    existing = cursor.fetchone()
    
    if existing:
        score_id, current_points = existing
        if current_points >= points:
            # Вычитаем баллы
            new_points = current_points - points
            
            if new_points == 0:
                # Если стало 0, удаляем запись
                cursor.execute("DELETE FROM scores WHERE id = ?", (score_id,))
                flash(f"Все баллы удалены (было {current_points}, вычтено {points})", "success")
            else:
                # Обновляем запись
                cursor.execute("""
                    UPDATE scores 
                    SET points = ? 
                    WHERE id = ?
                """, (new_points, score_id))
                flash(f"Вычтено {points} баллов. Текущий результат: {new_points}", "success")
            
            conn.commit()
            # Сбрасываем кеш после изменений
            invalidate_cache()
        else:
            flash(f"Ошибка: нельзя вычесть {points} баллов, так как у команды только {current_points} баллов на этой станции", "error")
    else:
        flash(f"Ошибка: у этой команды нет баллов на выбранной станции", "error")

    conn.close()
    return redirect(url_for("admin"))

@app.route("/delete_score/<int:score_id>", methods=["POST"])
@login_required
def delete_score(score_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scores WHERE id = ?", (score_id,))
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Запись удалена", "success")
    return redirect(url_for("admin"))

@app.route("/delete_all_teams", methods=["POST"])
@login_required
def delete_all_teams():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scores")
    cursor.execute("DELETE FROM teams")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='teams'")
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Все команды удалены", "success")
    return redirect(url_for("admin"))

@app.route("/delete_all_stations", methods=["POST"])
@login_required
def delete_all_stations():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM station_operators")
    cursor.execute("DELETE FROM scores")
    cursor.execute("DELETE FROM stations")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='stations'")
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Все станции удалены", "success")
    return redirect(url_for("admin"))

@app.route("/delete_all_scores", methods=["POST"])
@login_required
def delete_all_scores():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scores")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='scores'")
    conn.commit()
    conn.close()
    invalidate_cache()  # Сбрасываем кеш
    flash("Все баллы удалены", "success")
    return redirect(url_for("admin"))

# ========== МАРШРУТЫ ДЛЯ ОПЕРАТОРОВ СТАНЦИЙ ==========

@app.route("/operator/panel", methods=["GET", "POST"])
@station_operator_required
def operator_panel():
    """Панель оператора станции"""
    station_id = session.get('operator_station_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем информацию о станции
    cursor.execute("SELECT name FROM stations WHERE id = ?", (station_id,))
    station = cursor.fetchone()
    
    # Получаем все команды
    cursor.execute("SELECT id, name FROM teams ORDER BY name")
    teams = cursor.fetchall()
    
    # Получаем текущие баллы для этой станции
    cursor.execute("""
        SELECT scores.id, teams.name, scores.points
        FROM scores
        JOIN teams ON teams.id = scores.team_id
        WHERE scores.station_id = ?
        ORDER BY teams.name
    """, (station_id,))
    station_scores = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        "operator_panel.html",
        station_name=station[0] if station else "Неизвестная станция",
        teams=teams,
        scores=station_scores
    )

@app.route("/operator/save_score", methods=["POST"])
@station_operator_required
def operator_save_score():
    """Сохранение баллов оператором станции"""
    team_id = request.form.get("team_id")
    points = request.form.get("points")
    station_id = session.get('operator_station_id')

    if not team_id or not points:
        flash("Ошибка: не выбрана команда", "error")
        return redirect(url_for('operator_panel'))

    try:
        points = int(points)
        team_id = int(team_id)
    except ValueError:
        flash("Ошибка: некорректные данные", "error")
        return redirect(url_for('operator_panel'))

    if points <= 0:
        flash("Количество баллов должно быть положительным числом", "error")
        return redirect(url_for('operator_panel'))

    conn = get_db()
    cursor = conn.cursor()

    # Проверяем, есть ли уже запись
    cursor.execute("""
        SELECT points FROM scores 
        WHERE team_id = ? AND station_id = ?
    """, (team_id, station_id))
    
    existing = cursor.fetchone()
    
    if existing:
        # Если запись есть - добавляем баллы к существующим
        new_points = existing[0] + points
        cursor.execute("""
            UPDATE scores 
            SET points = ? 
            WHERE team_id = ? AND station_id = ?
        """, (new_points, team_id, station_id))
        flash(f"Добавлено {points} баллов к существующим. Текущий результат: {new_points}", "success")
    else:
        # Если записи нет - создаем новую
        cursor.execute("""
            INSERT INTO scores (team_id, station_id, points)
            VALUES (?, ?, ?)
        """, (team_id, station_id, points))
        flash(f"Добавлено {points} баллов", "success")

    conn.commit()
    conn.close()
    
    # Сбрасываем кеш после изменений
    invalidate_cache()

    return redirect(url_for('operator_panel'))

if __name__ == "__main__":
    init_db()
    
    # Оптимизация базы данных при запуске
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Добавляем индексы для ускорения
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_team ON scores(team_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_station ON scores(station_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_team_station ON scores(team_id, station_id)")
        # Включаем WAL режим
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        conn.commit()
        conn.close()
        print("✅ База данных оптимизирована")
    except Exception as e:
        print(f"⚠️ Ошибка оптимизации БД: {e}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)