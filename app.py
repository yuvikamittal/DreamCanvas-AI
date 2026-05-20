from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dreamcanvas-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dreamcanvas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'



class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    images   = db.relationship('Image', backref='user', lazy=True)

class Image(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    filename   = db.Column(db.String(200), nullable=False)
    prompt     = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



def generate_image(prompt):
    import urllib.parse
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"

    try:
        print(f"\n[Generating] Prompt: {prompt}")
        response = requests.get(url, timeout=120)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200 and "image" in response.headers.get("content-type", ""):
            return response.content, None
        return None, f"API error {response.status_code}"

    except requests.exceptions.Timeout:
        return None, "Request timed out. Please try again."
    except requests.exceptions.ConnectionError:
        return None, "Network connection error."
    except Exception as e:
        return None, str(e)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return render_template("register.html")

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash("Your account is created! Now please login.", "success")
        return redirect(url_for('login'))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user     = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password, password):
            flash("Username or password is incorrect.", "error")
            return render_template("login.html")

        login_user(user)
        return redirect(url_for('home'))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route("/gallery")
@login_required
def gallery():
    images = Image.query.filter_by(user_id=current_user.id)\
                        .order_by(Image.created_at.desc()).all()
    return render_template("gallery.html", images=images)


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    data   = request.get_json()
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400
    if len(prompt) > 1000:
        return jsonify({"error": "Prompt too long."}), 400

    image_bytes, error = generate_image(prompt)

    if image_bytes is None:
        return jsonify({"error": error or "Image generation failed."}), 500

    os.makedirs("static/images", exist_ok=True)
    filename = f"{current_user.id}_{int(time.time())}.png"
    path     = os.path.join("static", "images", filename)

    with open(path, "wb") as f:
        f.write(image_bytes)

   
    img = Image(filename=filename, prompt=prompt, user_id=current_user.id)
    db.session.add(img)
    db.session.commit()

    return jsonify({"image_url": f"/static/images/{filename}"})



@app.route("/image/<int:image_id>")
def view_image(image_id):
    img = Image.query.get_or_404(image_id)
    return render_template("view_image.html", img=img)


@app.route("/image/<int:image_id>/delete", methods=["POST"])
@login_required
def delete_image(image_id):
    img = Image.query.get_or_404(image_id)
    if img.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    
    path = os.path.join("static", "images", img.filename)
    if os.path.exists(path):
        os.remove(path)

    db.session.delete(img)
    db.session.commit()
    return redirect(url_for('gallery'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

    