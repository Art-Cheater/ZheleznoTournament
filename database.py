import sqlite3

DB_NAME = "event.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        station_id INTEGER,
        points INTEGER DEFAULT 0,
        UNIQUE(team_id, station_id),
        FOREIGN KEY(team_id) REFERENCES teams(id),
        FOREIGN KEY(station_id) REFERENCES stations(id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS station_operators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        station_id INTEGER NOT NULL,
        FOREIGN KEY(station_id) REFERENCES stations(id)
    )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("База данных создана")