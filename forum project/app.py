import os
import time
import psycopg2
from flask import Flask, request, redirect, session, send_from_directory
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = "projectc00l"

# --- Database Connection (PostgreSQL for Render.com) ---
def get_db():
    # Get database URL from environment variable (set in Render.com)
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    # Parse the database URL
    result = urlparse(DATABASE_URL)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port
    
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=database,
        user=username,
        password=password,
        host=hostname,
        port=port
    )
    return conn

# --- Initialize Database Tables ---
def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        about_me TEXT DEFAULT ''
    )""")
    
    # Threads
    c.execute("""
    CREATE TABLE IF NOT EXISTS threads (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id)
    )""")
    
    # Posts
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY,
        thread_id INTEGER REFERENCES threads(id),
        user_id INTEGER REFERENCES users(id),
        content TEXT NOT NULL
    )""")
    
    # User status (ban/timeout)
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_status (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        banned_reason TEXT,
        timeout_until INTEGER
    )""")
    
    # Direct Messages
    c.execute("""
    CREATE TABLE IF NOT EXISTS dms (
        id SERIAL PRIMARY KEY,
        sender_id INTEGER REFERENCES users(id),
        receiver_id INTEGER REFERENCES users(id),
        content TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )""")
    
    conn.commit()
    conn.close()

init_db()

# --- Helper: Current User ---
def current_user():
    if "user_id" not in session:
        return None
    uid = session["user_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT banned_reason, timeout_until FROM user_status WHERE user_id=%s", (uid,))
    status = c.fetchone()
    if status:
        if status[0]:  # banned_reason
            return ("banned", status[0])
        if status[1] and int(status[1]) > int(time.time()):  # timeout_until
            return ("timeout", status[1])
    c.execute("SELECT id, username FROM users WHERE id=%s", (uid,))
    u = c.fetchone()
    conn.close()
    if u:
        return (u[0], u[1])
    return None

# --- Page Rendering Helper (Same as Before) ---
def render_page(title, content):
    return f"""
<!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body{{font-family:Arial,sans-serif;background-color:#36393f;color:white;margin:0;padding:0;}}
            a{{color:#00aff4;text-decoration:none;}}
            a:hover{{text-decoration:underline;}}
            header{{background-color:#2f3136;padding:10px;color:white;}}
            .container{{display:flex;flex-wrap:wrap;}}
            .sidebar{{width:20%;padding:10px;background-color:#202225;}}
            .content{{width:80%;padding:10px;}}
            textarea,input{{width:100%;margin:5px 0;padding:5px;border-radius:5px;border:none;}}
            input[type=submit]{{background-color:#7289da;color:white;cursor:pointer;}}
            ul{{list-style:none;padding-left:0;}}
            @media(max-width:768px){{.container{{flex-direction:column;}}.sidebar,.content{{width:100%;}}}}
            .thread-list {{margin-top:20px;}}
            .thread-item {{background-color:#2f3136;padding:10px;margin-bottom:10px;border-radius:5px;}}
            .post-item {{background-color:#2f3136;padding:10px;margin-bottom:10px;border-radius:5px;}}
            .message {{background-color:#2f3136;padding:10px;margin-bottom:10px;border-radius:5px;}}
            form {{margin:20px 0;}}
        </style>
    </head>
    <body>
        <header>
            <a href="/">Forum Home</a>
        </header>
        <div class="container">
            <div class="content">
                {content}
            </div>
        </div>
    </body>
    </html>
    """

# --- Routes (Same as Before, but with PostgreSQL Syntax) ---
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password) VALUES (%s,%s)", (username, password))
            conn.commit()
            conn.close()
            return redirect("/login")
        except psycopg2.IntegrityError:
            return render_page("Signup", "Username already taken.")
    return render_page("Signup", """
    <h1>Signup</h1>
    <form method="post">
    Username: <input name="username"><br>
    Password: <input type="password" name="password"><br>
    <input type="submit" value="Signup">
    </form>
    <a href='/login'>Login</a>
    """)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=%s AND password=%s", (username, password))
        u = c.fetchone()
        conn.close()
        if u:
            session["user_id"] = u[0]
            return redirect("/")
        return render_page("Login", "Invalid credentials.")
    return render_page("Login", """
    <h1>Login</h1>
    <form method="post">
    Username: <input name="username"><br>
    Password: <input type="password" name="password"><br>
    <input type="submit" value="Login">
    </form>
    <a href='/signup'>Signup</a>
    """)

# --- Other Routes (Same as Before, but with PostgreSQL Syntax) ---
# (Continue with the rest of your routes, replacing SQLite syntax with PostgreSQL)

# --- Run App ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
