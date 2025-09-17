import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from uuid import uuid4
from supabase import create_client, Client
from dotenv import load_dotenv
from config import Config
from datetime import datetime, timezone



load_dotenv()

class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    SECRET_KEY = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

supabase_url = app.config['SUPABASE_URL']
supabase_key = app.config['SUPABASE_KEY']
supabase: Client = create_client(supabase_url, supabase_key)

def fetch_posts():
    resources_response = supabase.table('resource').select("*").execute()
    resources = resources_response.data

    posts = []
    for resource in resources:
        status_response = supabase.table('status_updates').select("*").eq('resource_id', resource['id']).order('created_at', desc=True).limit(1).execute()
        status = status_response.data[0] if status_response.data else None

        # Get upvote count by counting rows
        upvotes_response = supabase.table('upvotes').select('id', count='exact').eq('resource_id', resource['id']).execute()
        upvotes_count = upvotes_response.count if hasattr(upvotes_response, 'count') else len(upvotes_response.data)

        post = {
            'id': resource['id'],
            'title': resource['name'],
            'image_url': resource['image_url'],
            'description': status['status_message'] if status else '',
            'upvotes': upvotes_count,
            'comments': 0,  # Update if you track comments
            'crowd': status['crowd_level'] if status else '',
            'chips': status['chips_available'] if status else '',
            'queue': status['queue_length'] if status else ''
        }
        posts.append(post)
    posts.sort(key=lambda x: x['upvotes'], reverse=True)
    return posts

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

@app.route('/upvote', methods=['POST'])
def upvote():
    if 'username' not in session:
        return jsonify({'error': 'Login required'}), 401

    resource_id = request.json.get('resource_id')
    user_id = session.get('user_id')  # you'll want to store this at login

    # Prevent double upvote
    result = supabase.table('upvotes').select('*').eq('resource_id', resource_id).eq('user_id', user_id).execute()
    if result.data:
        return jsonify({'error': 'Already upvoted'}), 409

    supabase.table('upvotes').insert({
        'id': str(uuid4()),
        'resource_id': resource_id,
        'user_id': user_id
    }).execute()
    # Return new upvote count
    count = supabase.table('upvotes').select('id', count='exact').eq('resource_id', resource_id).execute().count
    return jsonify({'success': True, 'upvotes': count})

# Supabase configuration
supabase_url: str = app.config['SUPABASE_URL']
supabase_key: str = app.config['SUPABASE_KEY']
#supabase: Client = create_client(supabase_url, supabase_key)

# Custom decorator to check if user is logged in
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Custom decorator to check if user is admin
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('indexed'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/')
def index():
    posts = fetch_posts()
    return render_template('index.html', posts=posts, username=session.get('username'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        try:
            response = supabase.auth.sign_in_with_password({
                "email": username,
                "password": password
            })

            print("Supabase login response:", response)
            print("User object:", getattr(response, 'user', None))

            if getattr(response, 'user', None):
                session['username'] = username
                session['is_admin'] = False
                session['user_id'] = response.user.id
                return redirect(url_for('profile'))
            else:
                return render_template('login.html', error="Invalid credentials or unconfirmed email")
        except Exception as e:
            print("Login exception:", e)
            return render_template('login.html', error=f"Login failed: {str(e)}")

    return render_template('login.html')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            return render_template('register.html', error="Email and password required")

        try:
            # Register via Supabase Auth
            user_response = supabase.auth.sign_up({"email": email, "password": password})
            print("Signup response:", user_response)

            if user_response and user_response.user:
                user_id = user_response.user.id
                print("Supabase Auth user ID:", user_id)

                # Insert raw credentials into users table
                user_data = {
                    'id':user_response.user.id,
                    'email': email,
                    'password': password,  # ⚠️ stored as plain text
                }
                print("Inserting into users table:", user_data)
                supabase.table('user').insert(user_data).execute()
                print("Insert successful")

                # Set session
                session['username'] = email
                session['user_id'] = user_id

                return redirect(url_for('create_post'))

            else:
                return render_template('register.html', error="Registration failed")

        except Exception as e:
            print("Registration error:", e)
            return render_template('register.html', error=str(e))

    return render_template('register.html')


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', username=session['username'])

@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/update_post/<post_id>', methods=['POST'])
@login_required
def update_post(post_id):
    description = request.form['description']
    crowd = request.form['crowd']
    chips = request.form['chips']
    queue = request.form['queue']

    # Check if a status update exists for the resource
    status_response = supabase.table('status_updates').select("*").eq('resource_id', post_id).execute()
    status = status_response.data

    if status:
        # Update the existing status update
        supabase.table('status_updates').update({
            'crowd_level': crowd,
            'chips_available': chips,
            'queue_length': queue,
            'status_message': description
        }).eq('resource_id', post_id).execute()
    else:
        # Create a new status update
        supabase.table('status_updates').insert({
            'id': str(uuid4()),
            'resource_id': post_id,
            'crowd_level': crowd,
            'chips_available': chips,
            'queue_length': queue,
            'status_message': description
        }).execute()

    return redirect(url_for('index'))

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        print("create_post function called")
        try:
            # ✅ Re-authenticate client for RLS
            supabase.auth.set_session(session['access_token'], session['access_token'])

            title = request.form.get('title', '')
            description = request.form.get('description', '')
            crowd = request.form.get('crowd', '')
            chips = request.form.get('chips', '')
            queue = request.form.get('queue', '')

            resource_data = {
                'id': str(uuid4()),
                'content': {
                    'title': title,
                    'description': description,
                    'crowd': crowd,
                    'chips': chips,
                    'queue': queue
                },
                'created_by': session.get('user_id')
            }

            print("Inserting resource:", resource_data)
            supabase.table('resource').insert(resource_data).execute()

            # Optional: insert status update
            ...

            return redirect(url_for('index'))

        except Exception as e:
            print("Error in create_post:", e)
            return "Internal Server Error", 500

    return render_template('create_post.html')



if __name__ == '__main__':
    app.run(debug=True)
