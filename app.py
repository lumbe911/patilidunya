import os
import secrets
import smtplib
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

import cloudinary
import cloudinary.uploader
from flask import (Flask, render_template, redirect, url_for, request,
                   flash, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         current_user, login_required)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

database_url = os.environ.get('DATABASE_URL', '').strip()
if not database_url:
    database_url = 'sqlite:///catapp.db'
elif database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET', ''),
    secure=True
)

SITE_PRIVATE = os.environ.get('SITE_PRIVATE', '').strip().lower() in ('true', '1', 'yes')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '').strip()

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_SENDER = os.environ.get('MAIL_SENDER', MAIL_USERNAME)
SITE_URL = os.environ.get('SITE_URL', 'https://patilidunya.onrender.com')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Lutfen giris yapin.'
login_manager.login_message_category = 'warning'


def send_email(to_email, subject, html_body):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MAIL_SENDER
        msg['To'] = to_email
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_SENDER, to_email, msg.as_string())
        return True
    except Exception:
        return False


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), default='')
    bio = db.Column(db.Text, default='')
    avatar = db.Column(db.String(256), default='')
    reset_token = db.Column(db.String(256), nullable=True)
    reset_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cats = db.relationship('Cat', backref='owner', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')


class Cat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.String(50), default='')
    gender = db.Column(db.String(20), default='')
    color = db.Column(db.String(100), default='')
    description = db.Column(db.Text, default='')
    location = db.Column(db.String(200), default='')
    found_date = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    photos = db.relationship('CatPhoto', backref='cat', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='cat', lazy=True, cascade='all, delete-orphan')

    @property
    def like_count(self):
        return len(self.likes)


class CatPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    caption = db.Column(db.String(256), default='')
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'cat_id'),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    user = db.relationship('User', backref='comments')
    cat = db.relationship('Cat', backref=db.backref('comments', lazy=True, cascade='all, delete-orphan'))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side='Comment.id'), lazy=True)


class View(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'cat_id'),)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey('cat.id'), nullable=False)
    notif_type = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, default='')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    from_user = db.relationship('User', foreign_keys=[from_user_id])
    cat = db.relationship('Cat')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.before_request
def check_private_mode():
    if not SITE_PRIVATE:
        return
    ep = request.endpoint or ''
    if ep == 'static':
        return
    if current_user.is_authenticated:
        if ADMIN_USERNAME and current_user.username == ADMIN_USERNAME:
            return
        if not ADMIN_USERNAME:
            return
    if ep in ('index', 'login', 'register', 'logout'):
        return
    from flask import make_response
    html = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PatiliDunya</title>
<link rel="stylesheet" href="/static/css/style.css"></head>
<body style="display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:2rem;">
<div><h1 style="font-size:5rem;">&#128274;</h1>
<h2 style="font-weight:800;margin:1rem 0;">Site Simdilik Kapali</h2>
<p style="color:var(--gray-500);">Yakinda geri donucez!</p>
<p style="color:var(--gray-700);margin-top:0.5rem;font-weight:700;">Owner: Lumbe</p>
<a href="/login" style="color:var(--pink-600);font-weight:700;margin-top:1rem;display:inline-block;">Yonetici Giris</a></div>
</body></html>'''
    resp = make_response(html, 503)
    abort(resp)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'jfif', 'bmp', 'svg'}


def save_upload(file):
    if file and file.filename and allowed_file(file.filename):
        try:
            result = cloudinary.uploader.upload(file, folder="patilidunya")
            return result['secure_url']
        except Exception as e:
            print(f"CLOUDINARY ERROR: {e}")
            return None
    return None


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    return render_template('landing.html')


@app.route('/explore')
@login_required
def explore():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    query = Cat.query
    if q:
        like_pattern = f'%{q}%'
        query = query.filter(
            db.or_(
                Cat.name.ilike(like_pattern),
                Cat.color.ilike(like_pattern),
                Cat.location.ilike(like_pattern),
                Cat.description.ilike(like_pattern)
            )
        )
    cats = query.order_by(Cat.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template('explore.html', cats=cats, search_query=q)


@app.route('/reels')
@login_required
def reels():
    all_cats = Cat.query.order_by(Cat.created_at.desc()).all()
    cats_with_photo = [c for c in all_cats if c.photos]

    liked_ids = set()
    if current_user.is_authenticated:
        liked_ids = {l.cat_id for l in Like.query.filter_by(user_id=current_user.id).all()}

    comment_counts = {}
    for c in cats_with_photo:
        comment_counts[c.id] = Comment.query.filter_by(cat_id=c.id).count()

    return render_template('reels.html', cats=cats_with_photo, liked_ids=liked_ids, comment_counts=comment_counts)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=request.form.get('remember') is not None)
            flash('Hosgeldiniz!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('explore'))
        flash('Kullanici adi veya sifre hatali!', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        errors = []
        if len(username) < 3:
            errors.append('Kullanici adi en az 3 karakter olmali.')
        if len(password) < 6:
            errors.append('Sifre en az 6 karakter olmali.')
        if password != password2:
            errors.append('Sifreler eslesmiyor.')
        if User.query.filter_by(username=username).first():
            errors.append('Bu kullanici adi zaten alinmis.')
        if User.query.filter_by(email=email).first():
            errors.append('Bu e-posta zaten kayitli.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html')

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            display_name=username
        )
        db.session.add(user)
        db.session.commit()
        flash('Kayit basarili! Giris yapabilirsiniz.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        if user and user.email:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_url = SITE_URL + url_for('reset_password', token=token)
            html = f"""
            <div style="font-family:sans-serif; max-width:400px; margin:0 auto; padding:2rem;">
                <h2 style="color:#db2777;">🐱 PatiliDunya - Sifre Sifirlama</h2>
                <p>Merhaba <strong>{user.display_name or user.username}</strong>,</p>
                <p>Sifreni sifirlamak icin asagidaki linke tikla:</p>
                <a href="{reset_url}" style="display:inline-block; padding:0.8rem 1.5rem; background:linear-gradient(135deg,#ec4899,#a855f7); color:white; border-radius:9999px; text-decoration:none; font-weight:700; margin:1rem 0;">Sifremi Sifirla</a>
                <p style="color:#6b7280; font-size:0.85rem;">Bu link 1 saat icinde gecerlilgini yitirir.</p>
                <p style="color:#6b7280; font-size:0.85rem;">Eger bu istegi sen yapmadiysan, bu emaili gorunce ignorala.</p>
            </div>
            """
            sent = send_email(user.email, 'PatiliDunya - Sifre Sifirlama', html)
            if sent:
                flash('Sifre sifirlama emaili gonderildi! E-postani kontrol et.', 'success')
            else:
                flash('Email gonderilemedi. Daha sonra tekrar dene.', 'danger')
        else:
            flash('Boyle bir kullanici bulunamadi!', 'danger')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_expiry or user.reset_expiry < datetime.utcnow():
        flash('Gecersiz veya suresi dolmus link!', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if len(password) < 6:
            flash('Sifre en az 6 karakter olmali!', 'danger')
            return render_template('reset_password.html', token=token)
        if password != password2:
            flash('Sifreler eslesmiyor!', 'danger')
            return render_template('reset_password.html', token=token)
        user.password = generate_password_hash(password)
        user.reset_token = None
        user.reset_expiry = None
        db.session.commit()
        flash('Sifreniz basariyla degistirildi! Giris yapabilirsiniz.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)


@app.route('/profile/<username>')
@login_required
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    cats = Cat.query.filter_by(owner_id=user.id).order_by(Cat.created_at.desc()).all()
    cat_ids = [c.id for c in cats]
    total_likes = Like.query.filter(Like.cat_id.in_(cat_ids)).count() if cat_ids else 0
    total_comments = Comment.query.filter(Comment.cat_id.in_(cat_ids)).count() if cat_ids else 0
    total_views = View.query.filter(View.cat_id.in_(cat_ids)).count() if cat_ids else 0
    unread = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return render_template('user_profile.html', profile_user=user, cats=cats,
                           total_likes=total_likes, total_comments=total_comments,
                           total_views=total_views, unread=unread)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', '').strip()
        current_user.bio = request.form.get('bio', '').strip()

        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            filename = save_upload(avatar_file)
            if filename:
                current_user.avatar = filename

        db.session.commit()
        flash('Profil guncellendi!', 'success')
        return redirect(url_for('user_profile', username=current_user.username))
    return render_template('edit_profile.html')


@app.route('/cat/new', methods=['GET', 'POST'])
@login_required
def new_cat():
    if request.method == 'POST':
        cat = Cat(
            name=request.form.get('name', '').strip(),
            age=request.form.get('age', '').strip(),
            gender=request.form.get('gender', ''),
            color=request.form.get('color', '').strip(),
            description=request.form.get('description', '').strip(),
            location=request.form.get('location', '').strip(),
            found_date=request.form.get('found_date', '').strip(),
            owner_id=current_user.id
        )
        db.session.add(cat)
        db.session.commit()

        photos = request.files.getlist('photos')
        for photo in photos:
            print(f"UPLOADING: {photo.filename}")
            filename = save_upload(photo)
            print(f"CLOUDINARY RESULT: {filename}")
            if filename:
                db.session.add(CatPhoto(filename=filename, cat_id=cat.id))
        db.session.commit()

        flash(f'{cat.name} basariyla eklendi!', 'success')
        return redirect(url_for('cat_detail', cat_id=cat.id))
    return render_template('new_cat.html')


@app.route('/cat/<int:cat_id>')
@login_required
def cat_detail(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    existing_view = View.query.filter_by(user_id=current_user.id, cat_id=cat_id).first()
    if not existing_view:
        db.session.add(View(user_id=current_user.id, cat_id=cat_id))
        db.session.commit()
    liked = Like.query.filter_by(user_id=current_user.id, cat_id=cat_id).first() is not None
    is_fav = Favorite.query.filter_by(user_id=current_user.id, cat_id=cat_id).first() is not None
    view_count = View.query.filter_by(cat_id=cat_id).count()
    comments = Comment.query.filter_by(cat_id=cat_id).order_by(Comment.created_at.desc()).all()
    return render_template('cat_detail.html', cat=cat, liked=liked, comments=comments, is_fav=is_fav, view_count=view_count)


@app.route('/cat/<int:cat_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_cat(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    if cat.owner_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        cat.name = request.form.get('name', '').strip()
        cat.age = request.form.get('age', '').strip()
        cat.gender = request.form.get('gender', '')
        cat.color = request.form.get('color', '').strip()
        cat.description = request.form.get('description', '').strip()
        cat.location = request.form.get('location', '').strip()
        cat.found_date = request.form.get('found_date', '').strip()

        photos = request.files.getlist('photos')
        uploaded = 0
        for photo in photos:
            if photo and photo.filename:
                print(f"EDIT UPLOADING: {photo.filename}")
                filename = save_upload(photo)
                print(f"EDIT CLOUDINARY RESULT: {filename}")
                if filename:
                    db.session.add(CatPhoto(filename=filename, cat_id=cat.id))
                    uploaded += 1
        db.session.commit()
            flash(f'{uploaded} yeni fotograf yuklendi.', 'success')
        return redirect(url_for('cat_detail', cat_id=cat.id))
    return render_template('edit_cat.html', cat=cat)


@app.route('/cat/<int:cat_id>/delete', methods=['POST'])
@login_required
def delete_cat(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    if cat.owner_id != current_user.id:
        abort(403)
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    flash(f'{name} silindi.', 'info')
    return redirect(url_for('user_profile', username=current_user.username))


@app.route('/cat/<int:cat_id>/delete-photo/<int:photo_id>', methods=['POST'])
@login_required
def delete_photo(cat_id, photo_id):
    cat = Cat.query.get_or_404(cat_id)
    if cat.owner_id != current_user.id:
        abort(403)
    photo = CatPhoto.query.get_or_404(photo_id)
    if photo.cat_id != cat_id:
        abort(404)
    db.session.delete(photo)
    db.session.commit()
    flash('Fotograf silindi.', 'info')
    return redirect(url_for('edit_cat', cat_id=cat_id))


@app.route('/api/like/<int:cat_id>', methods=['POST'])
@login_required
def toggle_like(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    existing = Like.query.filter_by(user_id=current_user.id, cat_id=cat_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'liked': False, 'count': cat.like_count})
    else:
        like = Like(user_id=current_user.id, cat_id=cat_id)
        db.session.add(like)
        if cat.owner_id != current_user.id:
            notif = Notification(
                user_id=cat.owner_id, from_user_id=current_user.id,
                cat_id=cat_id, notif_type='like',
                    text=f'{current_user.display_name or current_user.username} "{cat.name}" begendi!'
            )
            db.session.add(notif)
        db.session.commit()
        return jsonify({'liked': True, 'count': cat.like_count})


@app.route('/cat/<int:cat_id>/comment', methods=['POST'])
@login_required
def add_comment(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    text = request.form.get('text', '').strip()
    if text:
        comment = Comment(text=text, user_id=current_user.id, cat_id=cat_id)
        db.session.add(comment)
        if cat.owner_id != current_user.id:
            notif = Notification(
                user_id=cat.owner_id, from_user_id=current_user.id,
                cat_id=cat_id, notif_type='comment',
                text=f'{current_user.display_name or current_user.username} kinen {cat.name} yorum yapti: {text[:50]}'
            )
            db.session.add(notif)
        db.session.commit()
    next_url = request.form.get('next', '')
    if next_url == 'reels':
        return redirect(url_for('reels'))
    return redirect(url_for('cat_detail', cat_id=cat_id))


@app.route('/api/comments/<int:cat_id>')
@login_required
def get_comments(cat_id):
    comments = Comment.query.filter_by(cat_id=cat_id, parent_id=None).order_by(Comment.created_at.desc()).limit(50).all()
    def serialize(c):
        return {
            'id': c.id,
            'text': c.text,
            'username': c.user.username,
            'display_name': c.user.display_name or c.user.username,
            'avatar': c.user.avatar or '',
            'time': c.created_at.strftime('%d %b'),
            'user_id': c.user_id,
            'replies': [serialize(r) for r in sorted(c.replies, key=lambda x: x.created_at)]
        }
    return jsonify({'comments': [serialize(c) for c in comments]})


@app.route('/cat/<int:cat_id>/comment/<int:comment_id>/reply', methods=['POST'])
@login_required
def reply_comment(cat_id, comment_id):
    parent = Comment.query.get_or_404(comment_id)
    cat = Cat.query.get_or_404(cat_id)
    text = request.form.get('text', '').strip()
    if text:
        reply = Comment(text=text, user_id=current_user.id, cat_id=cat_id, parent_id=comment_id)
        db.session.add(reply)
        if parent.user_id != current_user.id:
            notif = Notification(
                user_id=parent.user_id, from_user_id=current_user.id,
                cat_id=cat_id, notif_type='comment',
                text=f'{current_user.display_name or current_user.username} "{cat.name}" yorumuna yanit verdi: {text[:50]}'
            )
            db.session.add(notif)
        db.session.commit()
    next_url = request.form.get('next', '')
    if next_url == 'reels':
        return redirect(url_for('reels'))
    return redirect(url_for('cat_detail', cat_id=cat_id))


@app.route('/cat/<int:cat_id>/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(cat_id, comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    flash('Yorum silindi.', 'info')
    return redirect(url_for('cat_detail', cat_id=cat_id))


@app.route('/api/favorite/<int:cat_id>', methods=['POST'])
@login_required
def toggle_favorite(cat_id):
    existing = Favorite.query.filter_by(user_id=current_user.id, cat_id=cat_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'favorited': False})
    else:
        db.session.add(Favorite(user_id=current_user.id, cat_id=cat_id))
        db.session.commit()
        return jsonify({'favorited': True})


@app.route('/favorites')
@login_required
def favorites():
    favs = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
    cats = [Cat.query.get(f.cat_id) for f in favs if Cat.query.get(f.cat_id)]
    return render_template('favorites.html', cats=cats)


@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return render_template('notifications.html', notifications=notifs)


@app.route('/api/notifications/unread')
@login_required
def unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})


@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})


CITY_COORDS = {
    'istanbul': (41.0082, 28.9784), 'ankara': (39.9334, 32.8597), 'izmir': (38.4192, 27.1287),
    'bursa': (40.1885, 29.0610), 'antalya': (36.8969, 30.7133), 'konya': (37.8746, 32.4932),
    'trabzon': (41.0027, 39.7168),
}
NEIGHBORHOOD_COORDS = {
    'kadikoy': (40.9828, 29.0263), 'besiktas': (41.0422, 29.0068), 'sisli': (41.0602, 28.9874),
    'beyoglu': (41.0370, 28.9850), 'fatih': (41.0165, 28.9397), 'uskudar': (41.0234, 29.0152),
    'kartal': (40.8922, 29.1894), 'maltepe': (40.9357, 29.1462),
    'kizilay': (39.9199, 32.8543), 'cankaya': (39.9010, 32.8630), 'gazi': (39.9659, 32.8430),
    'alsancak': (38.4389, 27.1420), 'karsiyaka': (38.4489, 27.1715), 'bornova': (38.4705, 27.2248),
    'cesme': (38.3250, 26.3764), 'seferihisar': (38.1981, 26.8391), 'alacati': (38.2830, 26.3753),
    'nilufer': (40.2168, 28.9810), 'mudanya': (40.3759, 28.8833), 'goynuk': (40.4000, 29.1500),
    'inegol': (40.0787, 29.5095),
    'konyaalti': (36.8754, 30.6544), 'lara': (36.8529, 30.7918), 'side': (36.7670, 31.3880),
    'ortahisar': (41.0015, 39.7178),
}

def resolve_coords(location):
    loc = location.lower().strip()
    for key, coords in NEIGHBORHOOD_COORDS.items():
        if key in loc:
            return coords
    for key, coords in CITY_COORDS.items():
        if key in loc:
            return coords
    try:
        import urllib.request, urllib.parse, json, time
        q = urllib.parse.quote(loc + ', Turkey')
        url = 'https://nominatim.openstreetmap.org/search?q=' + q + '&format=json&limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'PatiliDunya/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data:
                return (float(data[0]['lat']), float(data[0]['lon']))
    except Exception:
        pass
    return None


@app.route('/map')
@login_required
def cat_map():
    cats = Cat.query.filter(Cat.location != '').all()
    cat_data = []
    for cat in cats:
        loc = cat.location.strip()
        if not loc:
            continue
        coords = resolve_coords(loc)
        if not coords:
            continue
        photo = cat.photos[0].filename if cat.photos else ''
        cat_data.append({
            'id': cat.id,
            'name': cat.name,
            'location': loc,
            'photo': photo,
            'gender': cat.gender,
            'likes': cat.like_count,
            'owner': cat.owner.display_name or cat.owner.username,
            'lat': coords[0],
            'lng': coords[1]
        })
    return render_template('cat_map.html', cat_data=cat_data)


@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.username != 'Lumbe':
        abort(403)
    users = User.query.order_by(User.created_at.desc()).all()
    user_data = []
    for u in users:
        user_data.append({
            'user': u,
            'cat_count': Cat.query.filter_by(owner_id=u.id).count(),
            'like_count': Like.query.join(Cat).filter(Cat.owner_id == u.id).count(),
            'comment_count': Comment.query.filter_by(user_id=u.id).count()
        })
    return render_template('admin_users.html', user_data=user_data, total=len(users))


@app.route('/admin/seed')
@login_required
def seed_cats():
    if current_user.username != 'Lumbe':
        abort(403)
    reset = request.args.get('reset') == '1'
    if reset:
        for cat in Cat.query.filter_by(owner_id=current_user.id).all():
            db.session.delete(cat)
        db.session.commit()
    elif Cat.query.count() > 0:
        flash('Zaten kayit var. /admin/seed?reset=1 ile sifirlayabilirsin.', 'warning')
        return redirect(url_for('explore'))
    import io
    import urllib.request
    seed_data = [
        {'name': 'Pamuk', 'gender': 'Female', 'color': 'Beyaz', 'location': 'Istanbul, Kadikoy', 'description': 'Sokakta buldum, cok uysal ve sevgi dolu. Kucağa gelmeyi cok seviyor.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/0XYvRd7oD.jpg'},
        {'name': 'Boncuk', 'gender': 'Female', 'color': 'Turuncu', 'location': 'Ankara, Cankaya', 'description': 'Bahce kedisi, veryali ve merakli. Her seyin ustune atlar.', 'age': '1 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mw.jpg'},
        {'name': 'Karabas', 'gender': 'Male', 'color': 'Siyah', 'location': 'Izmir, Alsancak', 'description': 'Sokak krali, cok cesur ve oyuncu. Herkesi tanir, kimseye korkmaz.', 'age': '3 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4NjY4Mg.jpg'},
        {'name': 'Seker', 'gender': 'Female', 'color': 'Gri-beyaz', 'location': 'Istanbul, Besiktas', 'description': 'Cok tatli, kucuk bir kedi. Insanlara cok yakin, sureli miyavlar.', 'age': '6 ay', 'photo': 'https://cdn2.thecatapi.com/images/MTk4NjY4Mw.jpg'},
        {'name': 'Tarcin', 'gender': 'Male', 'color': 'Kahverengi', 'location': 'Bursa, Nilufer', 'description': 'Buyuk ve guclu bir kedi. Yemek zamanini cok iyi bilir.', 'age': '4 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4NjY4MQ.jpg'},
        {'name': 'Luna', 'gender': 'Female', 'color': 'Turuncu-beyaz', 'location': 'Antalya, Konyaalti', 'description': 'Gece kedisi, yildizlari sever. Pencere kenarinda saatlerce oturur.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NQ.jpg'},
        {'name': 'Minik', 'gender': 'Male', 'color': 'Siyah-beyaz', 'location': 'Istanbul, Kadikoy', 'description': 'Cok kucuk ama cok cesur. Oyuncu ve enerjik, hic durmaz.', 'age': '4 ay', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Ng.jpg'},
        {'name': 'Peri', 'gender': 'Female', 'color': 'Gri', 'location': 'Izmir, Karsiyaka', 'description': 'Cok sessiz ve sakin bir kedi. Sevmeyi cok sever, huzur verir.', 'age': '1.5 yas', 'photo': 'https://cdn2.thecatapi.com/images/2m7.jpg'},
        {'name': 'Patates', 'gender': 'Male', 'color': 'Turuncu', 'location': 'Istanbul, Sisli', 'description': 'Tombul ve mutlu bir kedi. Yemek disinda pek hareket etmez.', 'age': '5 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2OA.jpg'},
        {'name': 'Duman', 'gender': 'Male', 'color': 'Gri', 'location': 'Ankara, Kizilay', 'description': 'Sokaktan geldi, cok sakin. Herkesle anlasir, diger kedilerle bile.', 'age': '3 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2MA.jpg'},
        {'name': 'Misket', 'gender': 'Female', 'color': 'Beyaz-turuncu', 'location': 'Izmir, Bornova', 'description': 'Cok oyuncu, top gibi ziplar. Enerjisi hic bitmez.', 'age': '8 ay', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2MQ.jpg'},
        {'name': 'Simo', 'gender': 'Male', 'color': 'Siyah', 'location': 'Istanbul, Beyoglu', 'description': 'Gece gezen kedi, sabah uyur. Ozgurlugu cok sever.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2MT.jpg'},
        {'name': 'Badem', 'gender': 'Female', 'color': 'Krem', 'location': 'Bursa, Mudanya', 'description': 'Bahce bahce dolanir, herkese selam verir. Cok sosyal.', 'age': '1 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mg.jpg'},
        {'name': 'Fistik', 'gender': 'Male', 'color': 'Kahverengi-beyaz', 'location': 'Antalya, Lara', 'description': 'Plaj kedisi, guneste uyumayi cok sever. Insanlara yakinlasir.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mj.jpg'},
        {'name': 'Zeytin', 'gender': 'Female', 'color': 'Siyah', 'location': 'Istanbul, Uskudar', 'description': 'Cok zeki, kapiyi acmayi ogrendi. Merakliligini gizleyemez.', 'age': '3 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mk.jpg'},
        {'name': 'Pati', 'gender': 'Male', 'color': 'Gri-beyaz', 'location': 'Ankara, Gazi', 'description': 'Uzun bacakli ve hizli. Kovalamaca oynamaya bayilir.', 'age': '1.5 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mw.jpg'},
        {'name': 'Ciko', 'gender': 'Male', 'color': 'Kahverengi', 'location': 'Izmir, Seferihisar', 'description': 'Balikci kedisi, deniz kenarinda yasar. Balik kokusunu alir.', 'age': '4 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NA.jpg'},
        {'name': 'Bono', 'gender': 'Female', 'color': 'Siyah-beyaz', 'location': 'Istanbul, Fatih', 'description': 'Iki renkli, cok guzel. Her gozu farkli bir hikaye anlatir.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2ND.jpg'},
        {'name': 'Pisi', 'gender': 'Female', 'color': 'Gri', 'location': 'Konya, Selcuklu', 'description': 'Sessiz gozlerle bakar ama her seyi anlar. Cok akillica.', 'age': '1 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NT.jpg'},
        {'name': 'Tomruk', 'gender': 'Male', 'color': 'Turuncu', 'location': 'Trabzon, Ortahisar', 'description': 'Dag kedisi, guclu ve bagimsiz. Ama gece gelir uyur.', 'age': '5 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NU.jpg'},
        {'name': 'Mavi', 'gender': 'Male', 'color': 'Gri', 'location': 'Istanbul, Kadikoy', 'description': 'Gozleri gri, ruhu ozgur. Kimseye baglanmaz ama herkesi sevir.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Nw.jpg'},
        {'name': 'Karamel', 'gender': 'Female', 'color': 'Altin', 'location': 'Izmir, Cesme', 'description': 'Yaz kedisi, yazin dogmus. Guneste parlar, guler yuzlu.', 'age': '1 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NQ.jpg'},
        {'name': 'Yaprak', 'gender': 'Female', 'color': 'Sari-beyaz', 'location': 'Bursa, Goynuk', 'description': 'Bahce cicekleri arasinda yasar. Cicek kokusunu cok sever.', 'age': '8 ay', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Nj.jpg'},
        {'name': 'Firtina', 'gender': 'Male', 'color': 'Siyah', 'location': 'Istanbul, Kartal', 'description': 'Cok hizli kosar, hic yorulmaz. Enerji topu gibi.', 'age': '1.5 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Ng.jpg'},
        {'name': 'Naz', 'gender': 'Female', 'color': 'Beyaz', 'location': 'Ankara, Cankaya', 'description': 'Nazli ve sevimli. Sevince gozlerini kisar, miyav der.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Nw.jpg'},
        {'name': 'Tarçin2', 'gender': 'Male', 'color': 'Kahverengi-cizgili', 'location': 'Istanbul, Maltepe', 'description': 'Cizgili kedi, kumsal gibi. Uyumayi ve yemegi cok sever.', 'age': '3 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2NT.jpg'},
        {'name': 'Suna', 'gender': 'Female', 'color': 'Turuncu', 'location': 'Antalya, Side', 'description': 'Turistik bolgede yasar, turistlere yakinlasir. Cok cana yakin.', 'age': '2 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Ng.jpg'},
        {'name': 'Kofte', 'gender': 'Male', 'color': 'Kahverengi', 'location': 'Bursa, Inegol', 'description': 'Inegol koftecisi kedisi. Yemek kokusuyla gelir, kofte bekler.', 'age': '4 yas', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mw.jpg'},
        {'name': 'Cilek', 'gender': 'Female', 'color': 'Pembe-beyaz', 'location': 'Izmir, Alacati', 'description': 'Pembe patili, tatli mi tatli. Herkesin gozdesi olur hemen.', 'age': '6 ay', 'photo': 'https://cdn2.thecatapi.com/images/MTk4ODA2Mg.jpg'},
    ]
    added = 0
    for i, item in enumerate(seed_data):
        cat = Cat(
            name=item['name'], age=item['age'], gender=item['gender'],
            color=item['color'], description=item['description'],
            location=item['location'], found_date='2026',
            owner_id=current_user.id
        )
        db.session.add(cat)
        db.session.commit()
        db.session.add(CatPhoto(filename=item['photo'], cat_id=cat.id))
        db.session.commit()
        added += 1
    flash(f'{added} ornek profil eklendi!', 'success')
    return redirect(url_for('explore'))


with app.app_context():
    db.create_all()
    try:
        db.session.execute(db.text('ALTER TABLE comment ADD COLUMN parent_id INTEGER'))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text('ALTER TABLE "user" ADD COLUMN reset_token VARCHAR(256)'))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text('ALTER TABLE "user" ADD COLUMN reset_expiry TIMESTAMP'))
        db.session.commit()
    except Exception:
        db.session.rollback()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
