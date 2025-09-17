import os
import sqlite3
import time
from flask import Flask, request, redirect, session, send_from_directory

app = Flask(__name__)
app.secret_key = "projectc00l"

# --- Database Path ---
DB_PATH = os.getenv("DATABASE_PATH", "forum.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- Setup database tables if they don't exist ---
def init_db():
    conn = get_db()
    c = conn.cursor()
    # Users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        about_me TEXT DEFAULT ''
    )""")
    # Threads
    c.execute("""
    CREATE TABLE IF NOT EXISTS threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        user_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    # Posts
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id INTEGER,
        user_id INTEGER,
        content TEXT NOT NULL,
        FOREIGN KEY(thread_id) REFERENCES threads(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    # User status (ban/timeout)
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_status (
        user_id INTEGER PRIMARY KEY,
        banned_reason TEXT,
        timeout_until INTEGER
    )""")
    # Direct Messages
    c.execute("""
    CREATE TABLE IF NOT EXISTS dms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        content TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        FOREIGN KEY(sender_id) REFERENCES users(id),
        FOREIGN KEY(receiver_id) REFERENCES users(id)
    )""")
    conn.commit()
    conn.close()

init_db()

# --- Helper: Current user ---
def current_user():
    if "user_id" not in session:
        return None
    uid = session["user_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT banned_reason, timeout_until FROM user_status WHERE user_id=?", (uid,))
    status = c.fetchone()
    if status:
        if status["banned_reason"]:
            return ("banned", status["banned_reason"])
        if status["timeout_until"] and int(status["timeout_until"]) > int(time.time()):
            return ("timeout", status["timeout_until"])
    c.execute("SELECT id,username FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    conn.close()
    if u:
        return (u["id"], u["username"])
    return None

# --- Page rendering helper ---
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

# --- Login / Signup / Logout ---
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)",(username,password))
            conn.commit()
            conn.close()
            return redirect("/login")
        except sqlite3.IntegrityError:
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
        c.execute("SELECT id FROM users WHERE username=? AND password=?",(username,password))
        u = c.fetchone()
        conn.close()
        if u:
            session["user_id"] = u["id"]
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

@app.route("/logout")
def logout():
    session.pop("user_id",None)
    return redirect("/")

# --- Forum index ---
@app.route("/")
def index():
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT threads.id,threads.title,users.username FROM threads LEFT JOIN users ON threads.user_id=users.id ORDER BY threads.id DESC")
    threads = c.fetchall()
    conn.close()
    html = "<h1>Forum</h1>"
    if user and isinstance(user[0], int):
        html += f"<div>Welcome {user[1]} | <a href='/logout'>Logout</a> | <a href='/profile/{user[0]}'>Profile</a> | <a href='/dms'>DMs</a></div>"
        html += "<a href='/new_thread' class='button'>New Thread</a>"
    else:
        html += "<div><a href='/login'>Login</a> | <a href='/signup'>Signup</a></div> | <div><a>CODED BY CRYPTED444/ALI</a>"
    
    html += "<div class='thread-list'>"
    for t in threads:
        html += f"<div class='thread-item'><a href='/thread/{t['id']}'>{t['title']}</a> by {t['username']}</div>"
    html += "</div>"
    return render_page("Section: Al-Dakhel's Class Forums", html)

@app.route("/new_thread", methods=["GET","POST"])
def new_thread():
    user = current_user()
    if not user or not isinstance(user[0], int):
        return redirect("/login")
    if request.method == "POST":
        title = request.form["title"]
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO threads (title,user_id) VALUES (?,?)",(title,user[0]))
        conn.commit()
        conn.close()
        return redirect("/")
    return render_page("New Thread", """
    <h1>New Thread</h1>
    <form method='post'>
    Title: <input name='title'><br>
    <input type='submit' value='Create'>
    </form><a href='/'>Back</a>
    """)

@app.route("/thread/<int:tid>", methods=["GET","POST"])
def thread_page(tid):
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST" and user and isinstance(user[0], int):
        content = request.form["content"]
        c.execute("INSERT INTO posts (thread_id,user_id,content) VALUES (?,?,?)",(tid,user[0],content))
        conn.commit()
    c.execute("SELECT title FROM threads WHERE id=?",(tid,))
    t = c.fetchone()
    if not t:
        conn.close()
        return render_page("Thread Not Found", "Thread not found.")
    c.execute("SELECT posts.id,posts.content,users.username FROM posts LEFT JOIN users ON posts.user_id=users.id WHERE thread_id=? ORDER BY posts.id",(tid,))
    posts = c.fetchall()
    conn.close()
    html = f"<h1>{t['title']}</h1>"
    if user and isinstance(user[0], int):
        html += f"<div>Welcome {user[1]} | <a href='/logout'>Logout</a> | <a href='/profile/{user[0]}'>Profile</a></div>"
    html += "<div class='post-list'>"
    for p in posts:
        html += f"<div class='post-item'>{p['username']}: {p['content']}</div>"
    html += "</div>"
    if user and isinstance(user[0], int):
        html += "<form method='post'><textarea name='content'></textarea><br><input type='submit' value='Post'></form>"
    html += "<a href='/'>Back</a>"
    return render_page(t['title'], html)

# --- Profiles ---
@app.route("/profile/<int:uid>", methods=["GET","POST"])
def profile(uid):
    user = current_user()
    if user and user[0] == "banned":
        return redirect(f"/banned/{user[1]}")
    if user and user[0] == "timeout":
        return render_page("Restricted", "You are temporarily restricted.")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username,about_me FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u:
        conn.close()
        return render_page("User Not Found", "User not found.")
    if request.method == "POST" and user and isinstance(user[0], int) and user[0] == uid:
        about = request.form.get("about_me","")
        c.execute("UPDATE users SET about_me=? WHERE id=?", (about,uid))
        conn.commit()
    conn.close()
    html = f"<h1>{u['username']}'s Profile</h1>"
    html += f"<div class='profile-info'>About me: {u['about_me']}</div>"
    if user and isinstance(user[0], int) and user[0] == uid:
        html += f"<form method='post'>Edit About Me:<br><textarea name='about_me'>{u['about_me']}</textarea><br><input type='submit' value='Update'></form>"
    html += "<a href='/'>Back</a>"
    return render_page(f"{u['username']}'s Profile", html)

# --- DM System ---
@app.route("/dms")
def list_dms():
    user = current_user()
    if not user or not isinstance(user[0], int):
        return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id,username FROM users WHERE id!=?", (user[0],))
    users = c.fetchall()
    html = "<h1>Direct Messages</h1><ul>"
    for u in users:
        html += f"<li><a href='/dm/{u['id']}'>{u['username']}</a></li>"
    html += "</ul><a href='/'>Back</a>"
    return render_page("Direct Messages", html)

@app.route("/dm/<int:uid>", methods=["GET","POST"])
def dm_convo(uid):
    user = current_user()
    if not user or not isinstance(user[0], int):
        return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u:
        conn.close()
        return render_page("User Not Found", "User not found.")
    if request.method == "POST":
        content = request.form.get("content","")
        if content:
            ts = int(time.time())
            c.execute("INSERT INTO dms (sender_id,receiver_id,content,timestamp) VALUES (?,?,?,?)", (user[0],uid,content,ts))
            conn.commit()
    c.execute("SELECT sender_id,content FROM dms WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) ORDER BY timestamp", (user[0],uid,uid,user[0]))
    messages = c.fetchall()
    conn.close()
    html = f"<h1>Conversation with {u['username']}</h1><ul>"
    for m in messages:
        html += f"<li class='message'>{'You' if m['sender_id']==user[0] else u['username']}: {m['content']}</li>"
    html += "</ul>"
    html += "<form method='post'><input name='content' placeholder='Message'><input type='submit' value='Send'></form>"
    html += "<a href='/dms'>Back</a>"
    return render_page(f"DM with {u['username']}", html)

# --- Admin Panel ---
ADMIN_USERS = [6]  # IDs with admin rights

@app.route("/admin", methods=["GET","POST"])
def admin_panel():
    user = current_user()
    if not user or not isinstance(user[0], int) or user[0] not in ADMIN_USERS:
        return render_page("Admin Panel", "Access denied.")
    msg = ""
    if request.method == "POST":
        action = request.form.get("action","")
        target_id = request.form.get("user_id","0")
        reason = request.form.get("reason","")
        duration = request.form.get("duration","0")
        try:
            target_id = int(target_id); duration = int(duration)
        except:
            target_id = 0; duration = 0
        conn = get_db()
        c = conn.cursor()
        if action == "ban":
            c.execute("INSERT OR REPLACE INTO user_status (user_id,banned_reason,timeout_until) VALUES (?,?,NULL)", (target_id,reason))
            msg = f"User {target_id} banned."
        elif action == "unban":
            c.execute("DELETE FROM user_status WHERE user_id=?", (target_id,))
            msg = f"User {target_id} unbanned."
        elif action == "timeout":
            c.execute("INSERT OR REPLACE INTO user_status (user_id,banned_reason,timeout_until) VALUES (?,?,?)", (target_id,None,int(time.time())+duration))
            msg = f"User {target_id} timed out."
        elif action == "delete_thread":
            c.execute("DELETE FROM threads WHERE id=?", (target_id,))
            msg = f"Thread {target_id} deleted."
        elif action == "delete_post":
            c.execute("DELETE FROM posts WHERE id=?", (target_id,))
            msg = f"Post {target_id} deleted."
        conn.commit()
        conn.close()
    html = f"<h1>Admin Panel</h1><p>{msg}</p>"
    html += """<form method='post'>
        Action: <select name='action'>
            <option value='ban'>Ban</option>
            <option value='unban'>Unban</option>
            <option value='timeout'>Timeout</option>
            <option value='delete_thread'>Delete Thread</option>
            <option value='delete_post'>Delete Post</option>
        </select><br>
        User/Thread/Post ID: <input name='user_id'><br>
        Reason (if ban): <input name='reason'><br>
        Timeout duration (seconds): <input name='duration'><br>
        <input type='submit' value='Execute'>
    </form><a href='/'>Back</a>"""
    return render_page("Admin Panel", html)

# --- Banned Page ---
@app.route("/banned/<reason>")
def banned_page(reason):
    return render_page("Banned", f"<h1>You are banned</h1><p>Reason: {reason}</p>")

# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

