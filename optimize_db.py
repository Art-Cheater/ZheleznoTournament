import sqlite3

DB_NAME = "event.db"

def optimize_database():
    """Оптимизация базы данных для производительности"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Добавляем индексы для ускорения запросов
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_team ON scores(team_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_station ON scores(station_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_team_station ON scores(team_id, station_id)")
    
    # Включаем WAL режим для лучшей конкурентности
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Оптимизируем настройки
    cursor.execute("PRAGMA cache_size=-20000")  # 20MB кеш
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    
    conn.commit()
    conn.close()
    print("✅ База данных оптимизирована")

if __name__ == "__main__":
    optimize_database()