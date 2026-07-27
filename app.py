import os
import secrets
from datetime import datetime

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

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Lutfen giris yapin.'
login_manager.login_message_category = 'warning'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), default='')
    bio = db.Column(db.Text, default='')
    avatar = db.Column(db.String(256), default='')
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
    user = db.relationship('User', backref='comments')
    cat = db.relationship('Cat', backref=db.backref('comments', lazy=True, cascade='all, delete-orphan'))


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
            login_user(user, remember=True)
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


@app.route('/profile/<username>')
@login_required
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    cats = Cat.query.filter_by(owner_id=user.id).order_by(Cat.created_at.desc()).all()
    return render_template('user_profile.html', profile_user=user, cats=cats)


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
    liked = False
    if current_user.is_authenticated:
        liked = Like.query.filter_by(user_id=current_user.id, cat_id=cat_id).first() is not None
    comments = Comment.query.filter_by(cat_id=cat_id).order_by(Comment.created_at.desc()).all()
    return render_template('cat_detail.html', cat=cat, liked=liked, comments=comments)


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
        flash(f'Kedi profili guncellendi! {uploaded} yeni fotograf yuklendi.', 'success')
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
    existing = Like.query.filter_by(user_id=current_user.id, cat_id=cat_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'liked': False, 'count': Cat.query.get(cat_id).like_count})
    else:
        like = Like(user_id=current_user.id, cat_id=cat_id)
        db.session.add(like)
        db.session.commit()
        return jsonify({'liked': True, 'count': Cat.query.get(cat_id).like_count})


@app.route('/cat/<int:cat_id>/comment', methods=['POST'])
@login_required
def add_comment(cat_id):
    cat = Cat.query.get_or_404(cat_id)
    text = request.form.get('text', '').strip()
    if text:
        comment = Comment(text=text, user_id=current_user.id, cat_id=cat_id)
        db.session.add(comment)
        db.session.commit()
    next_url = request.form.get('next', '')
    if next_url == 'reels':
        return redirect(url_for('reels'))
    return redirect(url_for('cat_detail', cat_id=cat_id))


@app.route('/api/comments/<int:cat_id>')
@login_required
def get_comments(cat_id):
    comments = Comment.query.filter_by(cat_id=cat_id).order_by(Comment.created_at.desc()).limit(50).all()
    return jsonify({'comments': [{
        'text': c.text,
        'username': c.user.username,
        'display_name': c.user.display_name or c.user.username,
        'avatar': c.user.avatar or '',
        'time': c.created_at.strftime('%d %b')
    } for c in comments]})


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
        flash('Zaten kedi var. /admin/seed?reset=1 ile sifirlayabilirsin.', 'warning')
        return redirect(url_for('explore'))
    import io
    import urllib.request
    seed_data = [
        {'name': 'Pamuk', 'gender': 'Female', 'color': 'Beyaz', 'location': 'Istanbul, Kadikoy', 'description': 'Sokakta buldum, cok uysal ve sevgi dolu. Gozleri masmavi.', 'age': '2 yas', 'photos': [
            'https://cataas.com/cat/says/Pamuk?fontSize=50&fontColor=white&type=or'
        ]},
        {'name': 'Boncuk', 'gender': 'Female', 'color': 'Turuncu', 'location': 'Ankara, Cankaya', 'description': 'Bahce kedisi, gozleri yesil. Miyavlama sesi cok tatli.', 'age': '1 yas', 'photos': [
            'https://cataas.com/cat/says/Boncuk?fontSize=50&fontColor=white&type=si'
        ]},
        {'name': 'Karabas', 'gender': 'Male', 'color': 'Siyah', 'location': 'Izmir, Alsancak', 'description': 'Sokak krali, cok cesur ve oyuncu. Herkesi tanir.', 'age': '3 yas', 'photos': [
            'https://cataas.com/cat/says/Karabas?fontSize=50&fontColor=white&type=fr'
        ]},
        {'name': 'Seker', 'gender': 'Female', 'color': 'Gri-beyaz', 'location': 'Istanbul, Besiktas', 'description': 'Cok tatli, kucuk bir kedi. Insanlara cok yakin.', 'age': '6 ay', 'photos': [
            'https://cataas.com/cat/says/Seker?fontSize=50&fontColor=white&type=or'
        ]},
        {'name': 'Tarcin', 'gender': 'Male', 'color': 'Kahverengi', 'location': 'Bursa, Nilufer', 'description': 'Buyuk ve guclu bir kedi. Patileri cok buyuk.', 'age': '4 yas', 'photos': [
            'https://cataas.com/cat/says/Tarcin?fontSize=50&fontColor=white&type=si'
        ]},
        {'name': 'Luna', 'gender': 'Female', 'color': 'Turuncu-beyaz', 'location': 'Antalya, Konyaalti', 'description': 'Gece kedisi, yildizlari sever. Cok gizemli.', 'age': '2 yas', 'photos': [
            'https://cataas.com/cat/says/Luna?fontSize=50&fontColor=white&type=or'
        ]},
        {'name': 'Minik', 'gender': 'Male', 'color': 'Siyah-beyaz', 'location': 'Istanbul, Kadikoy', 'description': 'Cok kucuk ama cok cesur. Oyuncu ve enerjik.', 'age': '4 ay', 'photos': [
            'https://cataas.com/cat/says/Minik?fontSize=50&fontColor=white&type=fr'
        ]},
        {'name': 'Peri', 'gender': 'Female', 'color': 'Gri', 'location': 'Izmir, Karsiyaka', 'description': 'Peri gibi guzel, cok sessiz ve sakin bir kedi.', 'age': '1.5 yas', 'photos': [
            'https://cataas.com/cat/says/Peri?fontSize=50&fontColor=white&type=sq'
        ]},
    ]
    added = 0
    for item in seed_data:
        cat = Cat(
            name=item['name'], age=item['age'], gender=item['gender'],
            color=item['color'], description=item['description'],
            location=item['location'], found_date='2026',
            owner_id=current_user.id
        )
        db.session.add(cat)
        db.session.commit()
        for photo_url in item['photos'][:1]:
            try:
                result = cloudinary.uploader.upload(photo_url, folder="patilidunya")
                db.session.add(CatPhoto(filename=result['secure_url'], cat_id=cat.id))
            except Exception as e:
                print(f"SEED PHOTO ERROR: {e}")
                db.session.add(CatPhoto(filename=photo_url, cat_id=cat.id))
        db.session.commit()
        added += 1
    flash(f'{added} ornek kedi eklendi!', 'success')
    return redirect(url_for('explore'))


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
