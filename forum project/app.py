from flask import Flask, request, redirect, session, send_from_directory
import sqlite3, os, time
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"
DB = "forum.db"
ADMIN_USERS = [1]  # Set admin IDs here

# --- Helpers ---
def get_db(): return sqlite3.connect(DB)

def current_user():
    if "user_id" in session:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, username, about_me FROM users WHERE id=?", (session["user_id"],))
        user = c.fetchone()
        if not user: return None
        c.execute("SELECT banned_reason,timeout_until FROM user_status WHERE user_id=?", (user[0],))
        status = c.fetchone()
        conn.close()
        if status:
            reason, timeout_until = status
            if reason: return ("banned", reason)
            if timeout_until: return ("timeout", timeout_until)
        return user
    return None

def html_page(title, body_html):
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        {body_html}
    </body>
    </html>
    """

# --- Initialize DB ---
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        about_me TEXT DEFAULT ''
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        user_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id INTEGER,
        content TEXT NOT NULL,
        user_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_status (
        user_id INTEGER PRIMARY KEY,
        banned_reason TEXT,
        timeout_until INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS dms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )''')
    conn.commit(); conn.close()

init_db()

# --- Static files ---
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# --- Homepage ---
@app.route('/')
def index():
    user = current_user()
    if user:
        if user[0] == "banned": return redirect(f'/banned/{user[1]}')
        if user[0] == "timeout": return html_page("Home", "You are temporarily restricted.")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT threads.id, threads.title, threads.user_id, users.username FROM threads LEFT JOIN users ON threads.user_id=users.id")
    threads = c.fetchall(); conn.close()

    html = "<header><h1>My Forum</h1><nav>"
    if user and type(user[0]) == int:
        html += f"Logged in as <b>{user[1]}</b> | <a href='/profile/{user[0]}'>Profile</a> | <a href='/dms'>DMs</a> | <a href='/logout'>Logout</a>"
        if user[0] in ADMIN_USERS: html += " | <a href='/admin'>Admin Panel</a>"
    else:
        html += "<a href='/login'>Login</a> | <a href='/signup'>Signup</a>"
    html += "</nav><div class='container'><div class='sidebar'>"
    html += "<form method='get' action='/search'><input type='text' name='q' placeholder='Search threads/posts...'><input type='submit' value='Search'></form></div><div class='content'>"
    if user and type(user[0]) == int:
        html += "<form action='/new_thread' method='post'><input name='title' placeholder='New thread title'><input type='submit' value='Create Thread'></form>"
    html += "<h2>Threads</h2><ul>"
    for tid, title, thread_user_id, uname in threads:
        html += f"<li><a href='/thread/{tid}'>{title}</a> by {uname if uname else 'Anonymous'}"
        if user and type(user[0])==int and (user[0]==thread_user_id or user[0] in ADMIN_USERS):
            html += f" <a href='/delete_thread/{tid}'>[Delete]</a>"
        html += "</li>"
    html += "</ul></div></div>"
    return html_page("Home", html)

# --- Banned ---
@app.route('/banned/<reason>')
def banned_page(reason):
    return html_page("Banned", f"<h1>You are banned</h1><p>Reason: {reason}</p>")

# --- Auth ---
BLOCKED_IDS = [2, 3]  # IDs blocked for all
MY_ID = 1  # Replace with your ID

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method=='POST':
        username=request.form['username']
        password=generate_password_hash(request.form['password'])
        conn=get_db(); c=conn.cursor()
        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)",(username,password))
            conn.commit(); conn.close(); return redirect('/login')
        except sqlite3.IntegrityError: return html_page("Signup","Username already exists!")
    return html_page("Signup","<form method='post'>Username: <input name='username'><br>Password: <input type='password' name='password'><br><input type='submit' value='Signup'></form>")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT id,password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        if user:
            if user[0] in BLOCKED_IDS and user[0] != MY_ID:
                return html_page("Login", "This account is blocked from logging in.")
            if check_password_hash(user[1], password):
                session['user_id'] = user[0]
                return redirect('/')
        return html_page("Login","Invalid credentials!")
    return html_page("Login","<form method='post'>Username: <input name='username'><br>Password: <input type='password' name='password'><br><input type='submit' value='Login'></form>")

@app.route('/logout')
def logout(): session.pop('user_id', None); return redirect('/')

# --- Threads/Posts ---
@app.route('/new_thread', methods=['POST'])
def new_thread():
    user=current_user()
    if not user or type(user[0])!=int: return redirect('/login')
    title=request.form['title']
    conn=get_db(); c=conn.cursor()
    c.execute("INSERT INTO threads (title,user_id) VALUES (?,?)",(title,user[0]))
    conn.commit(); conn.close(); return redirect('/')

@app.route('/thread/<int:tid>', methods=['GET','POST'])
def view_thread(tid):
    user=current_user()
    if user and user[0]=="banned": return redirect(f'/banned/{user[1]}')
    if user and user[0]=="timeout": return html_page("Thread", "You are temporarily restricted.")
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT title,user_id FROM threads WHERE id=?", (tid,))
    thread=c.fetchone()
    if not thread: conn.close(); return redirect('/')
    if request.method=='POST' and user and type(user[0])==int:
        content=request.form['content']
        c.execute("INSERT INTO posts (thread_id,user_id,content) VALUES (?,?,?)",(tid,user[0],content))
        conn.commit()
    c.execute("SELECT posts.id,posts.content,posts.user_id,users.username FROM posts LEFT JOIN users ON posts.user_id=users.id WHERE posts.thread_id=?", (tid,))
    posts=c.fetchall(); conn.close()
    html=f"<h1>{thread[0]}</h1>"
    if user and type(user[0])==int:
        html += "<form method='post'><textarea name='content' placeholder='Write a post'></textarea><br><input type='submit' value='Post'></form>"
    html += "<ul>"
    for pid, content, post_user_id, uname in posts:
        html += f"<li>{content} by {uname if uname else 'Anonymous'}"
        if user and type(user[0])==int and (user[0]==post_user_id or user[0] in ADMIN_USERS):
            html += f" <a href='/delete_post/{pid}'>[Delete]</a>"
        html += "</li>"
    html += "</ul><a href='/'>Back</a>"
    return html_page(thread[0], html)

# --- Delete ---
@app.route('/delete_thread/<int:tid>')
def delete_thread(tid):
    user=current_user()
    if not user or type(user[0])!=int: return redirect('/login')
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT user_id FROM threads WHERE id=?", (tid,))
    row = c.fetchone()
    if row and (row[0]==user[0] or user[0] in ADMIN_USERS):
        c.execute("DELETE FROM threads WHERE id=?", (tid,))
        conn.commit()
    conn.close(); return redirect('/')

@app.route('/delete_post/<int:pid>')
def delete_post(pid):
    user=current_user()
    if not user or type(user[0])!=int: return redirect('/login')
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT user_id FROM posts WHERE id=?", (pid,))
    row = c.fetchone()
    if row and (row[0]==user[0] or user[0] in ADMIN_USERS):
        c.execute("DELETE FROM posts WHERE id=?", (pid,))
        conn.commit()
    conn.close(); return redirect('/')

# --- Profiles ---
@app.route('/profile/<int:uid>', methods=['GET','POST'])
def profile(uid):
    user = current_user()
    if user and user[0]=="banned": return redirect(f'/banned/{user[1]}')
    if user and user[0]=="timeout": return html_page("Profile", "You are temporarily restricted.")
    conn=get_db(); c=conn.cursor()
    c.execute("SELECT username,about_me FROM users WHERE id=?", (uid,))
    u=c.fetchone()
    if not u: conn.close(); return html_page("Profile","User not found.")
    if request.method=='POST' and user and type(user[0])==int and user[0]==uid:
        about=request.form.get('about_me','')
        c.execute("UPDATE users SET about_me=? WHERE id=?", (about,uid))
        conn.commit()
    conn.close()
    html=f"<h1>{u[0]}'s Profile</h1><p>About me: {u[1]}</p>"
    if user and type(user[0])==int and user[0]==uid:
        html += "<form method='post'>Edit About Me:<br><textarea name='about_me'>{}</textarea><br><input type='submit' value='Update'></form>".format(u[1])
    html += "<a href='/'>Back</a>"
    return html_page(u[0], html)

# --- DM System ---
@app.route('/dms')
def list_dms():
    user = current_user()
    if not user or type(user[0]) != int:
        return redirect('/login')
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id != ?", (user[0],))
    users = c.fetchall(); conn.close()
    html = "<h1>Direct Messages</h1><ul>"
    for uid, uname in users:
        html += f"<li><a href='/dm/{uid}'>{uname}</a></li>"
    html += "</ul><a href='/'>Back</a>"
    return html_page("DMs", html)

@app.route('/dm/<int:uid>', methods=['GET', 'POST'])
def dm_convo(uid):
    user = current_user()
    if not user or type(user[0]) != int:
        return redirect('/login')
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u:
        conn.close()
        return html_page("DM", "User not found.")
    
    if request.method == 'POST':
        content = request.form.get('content', '')
        if content:
            ts = int(time.time())  # Current Unix timestamp
            c.execute(
                "INSERT INTO dms (sender_id, receiver_id, content, timestamp) VALUES (?, ?, ?, ?)",
                (user[0], uid, content, ts)
            )
            conn.commit()

    # Fetch all messages between users, ordered by timestamp
    c.execute("""
        SELECT sender_id, content, timestamp 
        FROM dms 
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) 
        ORDER BY timestamp ASC
    """, (user[0], uid, uid, user[0]))
    messages = c.fetchall(); conn.close()
    
    html = f"<h1>Conversation with {u[0]}</h1><ul>"
    for sender, content, ts in messages:
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        html += f"<li>[{time_str}] {'You' if sender==user[0] else u[0]}: {content}</li>"
    html += "</ul>"
    html += "<form method='post'><input name='content' placeholder='Message'><input type='submit' value='Send'></form>"
    html += "<a href='/dms'>Back</a>"
    return html_page(f"DM with {u[0]}", html)

# --- Admin Panel ---
@app.route('/admin', methods=['GET','POST'])
def admin_panel():
    user=current_user()
    if not user or type(user[0])!=int or user[0] not in ADMIN_USERS: return html_page("Admin","Access denied.")
    msg=""
    if request.method=='POST':
        action=request.form.get('action','')
        target_id=request.form.get('user_id','0')
        reason=request.form.get('reason','')
        duration=request.form.get('duration','0')
        try: target_id=int(target_id); duration=int(duration)
        except: target_id=0; duration=0
        conn=get_db(); c=conn.cursor()
        if action=='ban':
            c.execute("INSERT OR REPLACE INTO user_status (user_id,banned_reason,timeout_until) VALUES (?,?,NULL)", (target_id,reason))
            msg=f"User {target_id} banned."
        elif action=='timeout':
            c.execute("INSERT OR REPLACE INTO user_status (user_id,banned_reason,timeout_until) VALUES (?,?,?)", (target_id,None,duration))
            msg=f"User {target_id} timed out."
        elif action=='delete_thread':
            c.execute("DELETE FROM threads WHERE id=?", (target_id,))
            msg=f"Thread {target_id} deleted."
        elif action=='delete_post':
            c.execute("DELETE FROM posts WHERE id=?", (target_id,))
            msg=f"Post {target_id} deleted."
        conn.commit(); conn.close()
    html=f"<h1>Admin Panel</h1><p>{msg}</p>"
    html+="""<form method='post'>
        Action: <select name='action'>
            <option value='ban'>Ban</option>
            <option value='timeout'>Timeout</option>
            <option value='delete_thread'>Delete Thread</option>
            <option value='delete_post'>Delete Post</option>
        </select><br>
        User/Thread/Post ID: <input name='user_id'><br>
        Reason (if ban): <input name='reason'><br>
        Timeout duration (seconds): <input name='duration'><br>
        <input type='submit' value='Execute'>
    </form><a href='/'>Back</a>"""
    return html_page("Admin", html)

# --- Run App ---
if not os.path.exists("static"):
    os.makedirs("static")
with open("static/style.css","w") as f:
    f.write("""
body{font-family:Arial,sans-serif;background-color:#36393f;color:white;margin:0;padding:0;}
a{color:#00aff4;text-decoration:none;}
a:hover{text-decoration:underline;}
header{background-color:#2f3136;padding:10px;color:white;}
.container{display:flex;flex-wrap:wrap;}
.sidebar{width:20%;padding:10px;background-color:#202225;}
.content{width:80%;padding:10px;}
textarea,input{width:100%;margin:5px 0;padding:5px;border-radius:5px;border:none;}
input[type=submit]{background-color:#7289da;color:white;cursor:pointer;}
ul{list-style:none;padding-left:0;}
@media(max-width:768px){.container{flex-direction:column;}.sidebar,.content{width:100%;}}
    """)

app.run(debug=True)
